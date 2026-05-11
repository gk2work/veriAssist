from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class Mode(str, Enum):
    CHAT = "chat"
    DOCS = "docs"
    GENERATE = "generate"
    SVA = "sva"
    FORMAL = "formal"
    DEBUG = "debug"


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = Field(default_factory=list)
    mode: Mode = Mode.CHAT
    model: Optional[str] = None
    temperature: float = 0.3
    max_tokens: int = 4096


class ChatMessage(BaseModel):
    role: str
    content: str


class ModelInfo(BaseModel):
    name: str
    size: str
    quantization: str
    parameter_size: str
    modified_at: str


class HealthStatus(BaseModel):
    ollama: str
    models: list[str]
    default_model: str
    rag: dict = Field(default_factory=dict)
    sva2sby: str
    sby: str


# ── Phase 3: SVA Generation Models ───────────────────────

class SVAValidationResult(BaseModel):
    """Validation result from sv_validator."""
    valid: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    sva2sby_compatible: bool = True
    banned_constructs: list[str] = Field(default_factory=list)
    diagnostics: list[dict] = Field(default_factory=list)
    numbered_lines: list[dict] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)


class SVASource(BaseModel):
    """A RAG source citation."""
    source: str
    section: str = ""
    score: float = 0.0
    collection: str = ""


class SVAGenerateResponse(BaseModel):
    """Response from POST /api/sva/generate."""
    sva_code: str
    full_response: str
    validation: SVAValidationResult
    sva2sby_compatible: bool
    sources: list[SVASource] = Field(default_factory=list)
    retried: bool = False
    retry_reason: Optional[str] = None


# ── Phase 4: Formal Verification Models ──────────────────

class FormalRunRequest(BaseModel):
    description: Optional[str] = None
    sva_code: Optional[str] = None
    dut_files: list[str] = Field(default_factory=list)
    clock: str = "clk"
    reset: str = "rst_n"
    solver: str = "boolector"
    bmc_depth: int = 20
    mode: str = "bmc"


class FormalResult(BaseModel):
    """Result of a single property formal check."""
    property_name: str
    status: str
    depth: int = 0
    runtime_seconds: float = 0.0
    counterexample_vcd: Optional[str] = None
    message: str = ""


class FormalRunResponse(BaseModel):
    """Response from POST /api/formal/run."""
    job_id: str
    status: str
    results: list[FormalResult] = Field(default_factory=list)
    sva_code: Optional[str] = None
    validation: Optional[SVAValidationResult] = None


# ── Phase 5: Debug Analysis Models ───────────────────────

class DebugAnalysisResponse(BaseModel):
    """Response from POST /api/formal/debug/{job_id}."""
    summary: str = ""
    violation_cycle: int = -1
    violation_assertion: str = ""
    violation_description: str = ""
    signal_trace: list[dict] = Field(default_factory=list)
    root_cause: str = ""
    classification: str = ""
    suggested_fix: str = ""
    fixed_code: str = ""
    followup_properties: list[str] = Field(default_factory=list)
    model_used: str = ""
    analysis_time: float = 0.0


class RerunVerdict(BaseModel):
    """Verdict from POST /api/formal/rerun comparing with previous job."""
    fix_verdict: str = ""       # FIXED | NOT_FIXED | DIFFERENT_FAILURE | ERROR
    fix_message: str = ""
    previous_job_id: str = ""
    previous_status: str = ""


# ── Phase 6: UVM Generation Models ──────────────────────

class UVMSignal(BaseModel):
    """A signal in a DUT interface."""
    name: str
    width: int = 1
    direction: str = "input"
    msb: int = 0
    lsb: int = 0
    group: str = "data"
    is_clock: bool = False
    is_reset: bool = False


class UVMInterface(BaseModel):
    """Parsed DUT interface."""
    module_name: str = ""
    protocol: str = "generic"
    clock: str = "clk"
    reset: str = "rst_n"
    reset_active_low: bool = True
    parameters: dict = Field(default_factory=dict)
    signal_count: int = 0
    input_count: int = 0
    output_count: int = 0
    has_handshake: bool = False
    max_data_width: int = 32
    signals: list[UVMSignal] = Field(default_factory=list)


class UVMGeneratedFile(BaseModel):
    """A single generated UVM file."""
    filename: str
    content: str
    description: str = ""
    component_type: str = ""
    lines: int = 0


class UVMGenerateResponse(BaseModel):
    """Response from POST /api/uvm/generate."""
    success: bool = True
    name: str = ""
    protocol: str = ""
    file_count: int = 0
    total_lines: int = 0
    generation_time: float = 0.0
    interface: Optional[UVMInterface] = None
    interface_summary: str = ""
    files: list[UVMGeneratedFile] = Field(default_factory=list)
    error: str = ""
