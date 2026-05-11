"""
VeriAssist v2.0 — UVM Generation Router

POST /api/uvm/generate       — Generate complete UVM testbench from DUT or signals
POST /api/uvm/parse-interface — Parse DUT code and return interface analysis
GET  /api/uvm/protocols       — List supported protocols
"""

import logging
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.interface_parser import (
    parse_interface,
    format_interface_summary,
    interface_to_dict,
)
from app.services.uvm_generator import uvm_generator, UVMTestbench

logger = logging.getLogger("veriassist.uvm_router")
router = APIRouter(prefix="/api/uvm", tags=["uvm"])


# ═══════════════════════════════════════════════════════════════
# REQUEST MODELS
# ═══════════════════════════════════════════════════════════════

class SignalDef(BaseModel):
    name: str
    width: int = 1
    direction: str = "input"
    description: str = ""


class UVMGenerateRequest(BaseModel):
    dut_code: str = ""
    signal_list: list[SignalDef] = Field(default_factory=list)
    module_name: str = ""
    protocol: str = ""
    goals: str = ""
    name: str = ""             # base name for components (default: module_name)


class ParseInterfaceRequest(BaseModel):
    dut_code: str = ""
    signal_list: list[SignalDef] = Field(default_factory=list)
    module_name: str = ""
    protocol: str = ""


# ═══════════════════════════════════════════════════════════════
# POST /api/uvm/generate — Generate complete UVM testbench
# ═══════════════════════════════════════════════════════════════

@router.post("/generate")
async def generate_uvm(req: UVMGenerateRequest):
    """
    Generate a complete UVM testbench from DUT code or signal list.

    Provide either:
    - dut_code: SystemVerilog source code (interface auto-parsed)
    - signal_list: Manual signal definitions

    Returns all generated files with content, ready to save/compile.
    """
    if not req.dut_code and not req.signal_list:
        return {
            "error": "Provide either dut_code or signal_list",
            "hint": "Paste your DUT SystemVerilog code, or provide a list of signals with name/width/direction.",
        }

    try:
        # Parse interface
        signal_dicts = [s.model_dump() for s in req.signal_list] if req.signal_list else None

        iface = parse_interface(
            dut_code=req.dut_code,
            signal_list=signal_dicts,
            module_name=req.module_name,
            protocol_hint=req.protocol,
        )

        if not iface.signals:
            return {
                "error": "No signals found",
                "hint": "Could not parse any signals from the provided code or list. Check the module port declarations.",
            }

        # Generate testbench
        name = req.name or iface.module_name or "dut"
        tb = uvm_generator.generate(
            iface=iface,
            name=name,
            goals=req.goals,
        )

        # Build response
        return {
            "success": True,
            "name": tb.name,
            "protocol": tb.protocol,
            "file_count": tb.file_count,
            "total_lines": tb.total_lines,
            "generation_time": round(tb.generation_time, 3),
            "interface": interface_to_dict(iface),
            "interface_summary": format_interface_summary(iface),
            "files": [
                {
                    "filename": f.filename,
                    "content": f.content,
                    "description": f.description,
                    "component_type": f.component_type,
                    "lines": len(f.content.splitlines()),
                }
                for f in tb.files
            ],
        }

    except Exception as e:
        logger.error(f"UVM generation failed: {e}", exc_info=True)
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════
# POST /api/uvm/parse-interface — Parse DUT and return analysis
# ═══════════════════════════════════════════════════════════════

@router.post("/parse-interface")
async def parse_dut_interface(req: ParseInterfaceRequest):
    """
    Parse a DUT's interface without generating the testbench.
    Useful for previewing the detected signals, protocol, and grouping
    before committing to generation.
    """
    try:
        signal_dicts = [s.model_dump() for s in req.signal_list] if req.signal_list else None

        iface = parse_interface(
            dut_code=req.dut_code,
            signal_list=signal_dicts,
            module_name=req.module_name,
            protocol_hint=req.protocol,
        )

        return {
            "success": True,
            "interface": interface_to_dict(iface),
            "summary": format_interface_summary(iface),
        }

    except Exception as e:
        logger.error(f"Interface parsing failed: {e}", exc_info=True)
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════
# GET /api/uvm/protocols — List supported protocols
# ═══════════════════════════════════════════════════════════════

@router.get("/protocols")
async def list_protocols():
    """List all supported protocols with their key signals."""
    return {
        "protocols": [
            {
                "id": "axi",
                "name": "AXI4 / AXI4-Full",
                "key_signals": ["awvalid", "awready", "wvalid", "wready", "bvalid", "bready", "arvalid", "arready", "rvalid", "rready"],
                "description": "AMBA AXI4 full interface with burst support",
            },
            {
                "id": "axi_lite",
                "name": "AXI4-Lite",
                "key_signals": ["awvalid", "awready", "wvalid", "wready", "bvalid", "bready", "arvalid", "arready", "rvalid", "rready"],
                "description": "AMBA AXI4-Lite (no burst, no cache)",
            },
            {
                "id": "apb",
                "name": "APB",
                "key_signals": ["psel", "penable", "pready", "paddr", "pwdata", "prdata", "pwrite"],
                "description": "AMBA APB (Advanced Peripheral Bus)",
            },
            {
                "id": "spi",
                "name": "SPI",
                "key_signals": ["sclk", "mosi", "miso", "cs_n"],
                "description": "Serial Peripheral Interface",
            },
            {
                "id": "uart",
                "name": "UART",
                "key_signals": ["tx", "rx"],
                "description": "Universal Asynchronous Receiver-Transmitter",
            },
            {
                "id": "fifo",
                "name": "FIFO",
                "key_signals": ["wr_en", "rd_en", "wr_data", "rd_data", "full", "empty"],
                "description": "Synchronous FIFO interface",
            },
            {
                "id": "wishbone",
                "name": "Wishbone",
                "key_signals": ["cyc", "stb", "ack", "adr", "dat_i", "dat_o", "we"],
                "description": "Wishbone bus interface",
            },
            {
                "id": "generic",
                "name": "Generic",
                "key_signals": [],
                "description": "Auto-detect or custom interface",
            },
        ],
    }