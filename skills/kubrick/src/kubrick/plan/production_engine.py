#!/usr/bin/env python3
"""Canonical production engine for Kubrick first-class surfaces (v0.16).

Shared lifecycle used by design/script/image/video:

  request → validate → compile → artifact → receipt → result

Surfaces plug in via compilers; orchestration is not duplicated.
Composition over inheritance. Deterministic. Receipt-first. Fail closed.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from kubrick.plan.production_artifacts import write_artifact_tree as write_artifact_tree
from kubrick.runtime.provenance import provenance_bucket

SCHEMA_VERSION = "0.16.0"
SURFACES = frozenset({"design", "script", "image", "video"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProductionContext:
    """Shared project context for all surfaces."""

    project_id: str = "local-project"
    design_revision: str | None = None
    script_revision: str | None = None
    source_state_id: str | None = None
    provider: str = "generic"
    working_dir: str | None = None
    extras: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["extras"] = dict(self.extras)
        return data


@dataclass(frozen=True)
class ProductionRequest:
    """Normalized request into the production engine."""

    surface: str
    action: str
    brief: str | None = None
    input_text: str | None = None
    evidence: str | None = None
    design_text: str | None = None
    provider: str = "generic"
    project_id: str = "local-project"
    format: str = "markdown"
    duration: float = 8.0
    output: str | None = None
    context: ProductionContext | None = None

    def __post_init__(self) -> None:
        if self.surface not in SURFACES:
            raise ValueError(f"unknown surface: {self.surface}")


@dataclass
class ProductionArtifact:
    """Primary structured artifact produced by a surface action."""

    artifact_id: str
    artifact_type: str
    surface: str
    action: str
    project_id: str
    authority: str
    status: str
    payload: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    not_computable: list[str] = field(default_factory=list)
    source_design_revision: str | None = None
    source_script_revision: str | None = None
    source_state_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProductionReceipt:
    """Receipt-first execution record (hashable, auditable)."""

    receipt_id: str
    receipt_hash: str
    schema_version: str
    timestamp: str
    surface: str
    action: str
    version: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    warnings: list[str]
    validation: dict[str, Any]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProductionResult:
    """Engine result wrapping artifact + receipt + optional markdown body."""

    status: str
    authority: str
    surface: str
    action: str
    artifact: ProductionArtifact
    receipt: ProductionReceipt
    document_markdown: str | None = None
    diagnostic: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Legacy-compatible envelope used by existing CLI/tests."""
        body: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "artifact_id": self.artifact.artifact_id,
            "artifact_type": self.artifact.artifact_type,
            "surface": self.surface,
            "action": self.action,
            "status": self.status,
            "authority": self.authority,
            "project_id": self.artifact.project_id,
            "generated_at": self.receipt.timestamp,
            "source_state_id": self.artifact.source_state_id,
            "provenance": self.receipt.provenance,
            "shared_invariants": {
                "preserve_identity": True,
                "preserve_locked_facts": True,
                "preserve_ownership": True,
                "preserve_chronology": True,
                "preserve_geometry": True,
                "preserve_material_state": True,
                "preserve_residue": True,
            },
            "not_computable": list(self.artifact.not_computable),
            "result": dict(self.artifact.payload),
            "receipt": self.receipt.to_dict(),
            "warnings": list(self.artifact.warnings),
        }
        if self.document_markdown is not None:
            body["result"]["document_markdown"] = self.document_markdown
        if self.artifact.source_design_revision:
            body["source_design_revision"] = self.artifact.source_design_revision
            body["result"]["source_design_revision"] = self.artifact.source_design_revision
        if self.artifact.source_script_revision:
            body["source_script_revision"] = self.artifact.source_script_revision
        if self.diagnostic:
            body["diagnostic"] = self.diagnostic
        return body


class ProductionValidator:
    """Shared validation framework for production requests and compiler outputs."""

    @staticmethod
    def validate_request(request: ProductionRequest) -> dict[str, Any]:
        errors: list[str] = []
        if request.surface not in SURFACES:
            errors.append(f"unknown surface {request.surface}")
        if not request.action:
            errors.append("action required")
        return {"status": "VALID" if not errors else "INVALID", "errors": errors}

    @staticmethod
    def validate_compiler_output(payload: dict[str, Any]) -> dict[str, Any]:
        errors: list[str] = []
        if "status" not in payload:
            errors.append("compiler output missing status")
        if payload.get("status") == "NOT_COMPUTABLE" and "diagnostic" not in payload:
            errors.append("NOT_COMPUTABLE output missing diagnostic")
        return {"status": "VALID" if not errors else "INVALID", "errors": errors}


CompilerFn = Callable[[Any], dict[str, Any]]


class ProductionSurface:
    """One first-class surface bound to the shared engine lifecycle."""

    def __init__(self, name: str, actions: Mapping[str, CompilerFn] | None = None) -> None:
        if name not in SURFACES:
            raise ValueError(f"unknown surface: {name}")
        self.name = name
        self._actions: dict[str, CompilerFn] = dict(actions or {})

    def register(self, action: str, compiler: CompilerFn) -> None:
        self._actions[action] = compiler

    @property
    def actions(self) -> frozenset[str]:
        return frozenset(self._actions)

    def execute(self, request: ProductionRequest) -> ProductionResult:
        if request.surface != self.name:
            raise ValueError(f"surface mismatch: {request.surface} != {self.name}")
        return ProductionEngine.execute(request, self._actions.get(request.action))


class ProductionEngine:
    """Shared orchestration: validate → compile → wrap artifact/receipt."""

    @staticmethod
    def execute(request: ProductionRequest, compiler: CompilerFn | None) -> ProductionResult:
        req_validation = ProductionValidator.validate_request(request)
        timestamp = _now()
        input_fingerprint = {
            "surface": request.surface,
            "action": request.action,
            "brief": (request.brief or "")[:2000],
            "input": (request.input_text or "")[:2000],
            "evidence": (request.evidence or "")[:2000],
            "design": (request.design_text or "")[:2000],
            "provider": request.provider,
            "project_id": request.project_id,
            "format": request.format,
            "duration": request.duration,
        }
        receipt_hash = _digest(input_fingerprint)[:32]
        receipt_id = f"receipt-{receipt_hash[:16]}"

        if req_validation["status"] != "VALID":
            artifact = ProductionArtifact(
                artifact_id=f"kubrick-{request.surface}-{request.action}-{receipt_hash[:16]}",
                artifact_type="production-validation-failure",
                surface=request.surface,
                action=request.action,
                project_id=request.project_id,
                authority="NOT_COMPUTABLE",
                status="NOT_COMPUTABLE",
                payload={},
                not_computable=["request"],
            )
            receipt = ProductionReceipt(
                receipt_id=receipt_id,
                receipt_hash=receipt_hash,
                schema_version=SCHEMA_VERSION,
                timestamp=timestamp,
                surface=request.surface,
                action=request.action,
                version=SCHEMA_VERSION,
                inputs=input_fingerprint,
                outputs={},
                warnings=[],
                validation=req_validation,
                provenance=provenance_bucket(observed=["request"]),
            )
            return ProductionResult(
                status="NOT_COMPUTABLE",
                authority="NOT_COMPUTABLE",
                surface=request.surface,
                action=request.action,
                artifact=artifact,
                receipt=receipt,
                diagnostic={"code": "INVALID_REQUEST", "message": "; ".join(req_validation["errors"])},
            )

        if compiler is None:
            artifact = ProductionArtifact(
                artifact_id=f"kubrick-{request.surface}-{request.action}-{receipt_hash[:16]}",
                artifact_type="unknown-action",
                surface=request.surface,
                action=request.action,
                project_id=request.project_id,
                authority="NOT_COMPUTABLE",
                status="NOT_COMPUTABLE",
                payload={},
                not_computable=["action"],
            )
            receipt = ProductionReceipt(
                receipt_id=receipt_id,
                receipt_hash=receipt_hash,
                schema_version=SCHEMA_VERSION,
                timestamp=timestamp,
                surface=request.surface,
                action=request.action,
                version=SCHEMA_VERSION,
                inputs=input_fingerprint,
                outputs={},
                warnings=[],
                validation={"status": "INVALID", "errors": [f"No compiler for {request.surface}:{request.action}"]},
                provenance=provenance_bucket(observed=["request"]),
            )
            return ProductionResult(
                status="NOT_COMPUTABLE",
                authority="NOT_COMPUTABLE",
                surface=request.surface,
                action=request.action,
                artifact=artifact,
                receipt=receipt,
                diagnostic={
                    "code": "UNKNOWN_ACTION",
                    "message": f"No domain compiler for {request.surface}:{request.action}",
                },
            )

        # Adapters: compilers currently accept argparse Namespace-like objects.
        args = _RequestArgs(request)
        raw = compiler(args)
        out_validation = ProductionValidator.validate_compiler_output(raw)

        status = str(raw.get("status") or "PROPOSED")
        authority = str(raw.get("authority") or "PROPOSED")
        result_payload = dict(raw.get("result") or {})
        document = None
        if isinstance(result_payload.get("document_markdown"), str):
            document = result_payload.pop("document_markdown")

        artifact = ProductionArtifact(
            artifact_id=str(raw.get("artifact_id") or f"kubrick-{request.surface}-{request.action}-{receipt_hash[:16]}"),
            artifact_type=str(raw.get("artifact_type") or f"{request.surface}-{request.action}"),
            surface=request.surface,
            action=request.action,
            project_id=str(raw.get("project_id") or request.project_id),
            authority=authority,
            status=status,
            payload=result_payload,
            warnings=list(raw.get("warnings") or []),
            not_computable=list(raw.get("not_computable") or []),
            source_design_revision=raw.get("source_design_revision")
            or (result_payload.get("source_design_revision") if isinstance(result_payload, dict) else None),
            source_script_revision=raw.get("source_script_revision")
            or (result_payload.get("source_script_revision") if isinstance(result_payload, dict) else None),
            source_state_id=raw.get("source_state_id"),
        )
        outputs = {
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "status": status,
            "has_document": document is not None,
        }
        receipt = ProductionReceipt(
            receipt_id=receipt_id,
            receipt_hash=_digest({**input_fingerprint, "outputs": outputs, "status": status})[:32],
            schema_version=SCHEMA_VERSION,
            timestamp=timestamp,
            surface=request.surface,
            action=request.action,
            version=SCHEMA_VERSION,
            inputs=input_fingerprint,
            outputs=outputs,
            warnings=list(artifact.warnings),
            validation=out_validation,
            provenance=raw.get("provenance") or provenance_bucket(observed=[k for k, v in input_fingerprint.items() if v]),
        )
        return ProductionResult(
            status=status,
            authority=authority,
            surface=request.surface,
            action=request.action,
            artifact=artifact,
            receipt=receipt,
            document_markdown=document,
            diagnostic=raw.get("diagnostic") if isinstance(raw.get("diagnostic"), dict) else None,
        )


class _RequestArgs:
    """Namespace shim so existing surface_compilers COMPILERS keep working."""

    def __init__(self, request: ProductionRequest) -> None:
        self.brief = request.brief
        self.provider = request.provider
        self.project_id = request.project_id
        self.format = request.format
        self.duration = request.duration
        self.output = request.output
        self._loaded_input = request.input_text
        self._loaded_evidence = request.evidence
        # Prefer explicit design text; fall back to context-linked design revision marker.
        design = request.design_text
        if not design and request.context and request.context.design_revision:
            design = f"# Design: {request.project_id}\n\nRevision: `{request.context.design_revision}`\n"
        self._loaded_design = design
        if request.context and request.context.provider and request.provider == "generic":
            self.provider = request.context.provider
        if request.context and request.context.project_id:
            self.project_id = request.context.project_id


def build_surface(name: str) -> ProductionSurface:
    """Factory: bind one surface to all registered domain compilers."""
    from kubrick.surfaces.surface_compilers import COMPILERS

    actions = {action: fn for (surf, action), fn in COMPILERS.items() if surf == name}
    return ProductionSurface(name, actions)


def run_production(
    surface: str,
    action: str,
    *,
    brief: str | None = None,
    input_text: str | None = None,
    evidence: str | None = None,
    design_text: str | None = None,
    provider: str = "generic",
    project_id: str = "local-project",
    format: str = "markdown",
    duration: float = 8.0,
    context: ProductionContext | None = None,
) -> ProductionResult:
    """Public one-shot API for the shared production lifecycle."""
    request = ProductionRequest(
        surface=surface,
        action=action,
        brief=brief,
        input_text=input_text,
        evidence=evidence,
        design_text=design_text,
        provider=provider,
        project_id=project_id,
        format=format,
        duration=duration,
        context=context,
    )
    return build_surface(surface).execute(request)
