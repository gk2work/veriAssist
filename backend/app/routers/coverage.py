"""
VeriAssist v2.0 — Coverage Advisor Router

POST /api/coverage/analyze     — Analyze DUT for coverage opportunities
POST /api/coverage/generate    — Generate complete coverage model
POST /api/coverage/recommend   — Get sequence recommendations for gaps
GET  /api/coverage/protocols   — Protocol-specific coverage patterns
"""

import logging
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.interface_parser import parse_interface, interface_to_dict
from app.services.coverage_analyzer import (
    coverage_analyzer,
    format_analysis_summary,
    CoverageAnalysis,
)
from app.services.coverage_generator import coverage_generator

logger = logging.getLogger("veriassist.coverage_router")
router = APIRouter(prefix="/api/coverage", tags=["coverage"])


# ═══════════════════════════════════════════════════════════════
# REQUEST MODELS
# ═══════════════════════════════════════════════════════════════

class CoverageAnalyzeRequest(BaseModel):
    dut_code: str
    protocol: str = ""
    module_name: str = ""


class CoverageGenerateRequest(BaseModel):
    dut_code: str
    protocol: str = ""
    module_name: str = ""
    name: str = ""


class CoverageRecommendRequest(BaseModel):
    dut_code: str
    protocol: str = ""
    priority: str = ""       # filter: "high" | "medium" | "low" | "" (all)


# ═══════════════════════════════════════════════════════════════
# POST /api/coverage/analyze — Analyze DUT
# ═══════════════════════════════════════════════════════════════

@router.post("/analyze")
async def analyze_coverage(req: CoverageAnalyzeRequest):
    """
    Analyze a DUT for coverage opportunities.

    Returns:
    - Detected FSMs with states and transitions
    - Coverage opportunities categorized by type and priority
    - Signal classification and protocol detection
    - Coverpoint hints and sequence suggestions per opportunity
    """
    if not req.dut_code.strip():
        return {"error": "No DUT code provided"}

    try:
        # Parse interface for signal classification
        iface = parse_interface(
            dut_code=req.dut_code,
            module_name=req.module_name,
            protocol_hint=req.protocol,
        )

        # Run analysis
        analysis = coverage_analyzer.analyze(
            dut_code=req.dut_code,
            iface=iface,
            protocol=req.protocol,
        )

        return {
            "success": True,
            "module_name": analysis.module_name,
            "protocol": analysis.protocol,
            "interface": interface_to_dict(iface),
            "summary": format_analysis_summary(analysis),
            "stats": {
                "total_opportunities": analysis.total_opportunities,
                "high_priority": analysis.high_priority,
                "medium_priority": analysis.medium_priority,
                "low_priority": analysis.low_priority,
                "fsm_count": len(analysis.fsms),
            },
            "fsms": [
                {
                    "state_reg": fsm.state_reg,
                    "width": fsm.width,
                    "states": fsm.states,
                    "transitions": fsm.transitions,
                    "reset_state": fsm.reset_state,
                    "has_default": fsm.has_default,
                }
                for fsm in analysis.fsms
            ],
            "opportunities": [
                {
                    "category": opp.category,
                    "name": opp.name,
                    "description": opp.description,
                    "priority": opp.priority,
                    "signals": opp.signals,
                    "coverpoint_hint": opp.coverpoint_hint,
                    "sequence_hint": opp.sequence_hint,
                }
                for opp in analysis.opportunities
            ],
            "analysis_time": round(analysis.analysis_time, 4),
        }

    except Exception as e:
        logger.error(f"Coverage analysis failed: {e}", exc_info=True)
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════
# POST /api/coverage/generate — Generate coverage model
# ═══════════════════════════════════════════════════════════════

@router.post("/generate")
async def generate_coverage(req: CoverageGenerateRequest):
    """
    Generate a complete coverage model for a DUT.

    Returns:
    - SystemVerilog covergroup code with protocol-aware bins
    - UVM subscriber wrapper class
    - Sequence recommendations with code
    - Coverage verification checklist
    """
    if not req.dut_code.strip():
        return {"error": "No DUT code provided"}

    try:
        iface = parse_interface(
            dut_code=req.dut_code,
            module_name=req.module_name,
            protocol_hint=req.protocol,
        )

        model = coverage_generator.generate(
            dut_code=req.dut_code,
            iface=iface,
            protocol=req.protocol,
            name=req.name or iface.module_name or "dut",
        )

        return {
            "success": True,
            "covergroup_code": model.covergroup_code,
            "subscriber_code": model.subscriber_code,
            "total_coverpoints": model.total_coverpoints,
            "total_crosses": model.total_crosses,
            "analysis_summary": model.analysis_summary,
            "recommendations": [
                {
                    "name": rec.name,
                    "description": rec.description,
                    "priority": rec.priority,
                    "target_coverage": rec.target_coverage,
                    "sequence_code": rec.sequence_code,
                }
                for rec in model.recommendations
            ],
            "checklist": model.checklist,
            "generation_time": round(model.generation_time, 4),
        }

    except Exception as e:
        logger.error(f"Coverage generation failed: {e}", exc_info=True)
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════
# POST /api/coverage/recommend — Sequence recommendations only
# ═══════════════════════════════════════════════════════════════

@router.post("/recommend")
async def recommend_sequences(req: CoverageRecommendRequest):
    """
    Get sequence recommendations to close coverage gaps.
    Optionally filter by priority level.
    """
    if not req.dut_code.strip():
        return {"error": "No DUT code provided"}

    try:
        iface = parse_interface(
            dut_code=req.dut_code,
            protocol_hint=req.protocol,
        )

        model = coverage_generator.generate(
            dut_code=req.dut_code,
            iface=iface,
            protocol=req.protocol,
        )

        recs = model.recommendations
        if req.priority:
            recs = [r for r in recs if r.priority == req.priority]

        return {
            "success": True,
            "count": len(recs),
            "recommendations": [
                {
                    "name": rec.name,
                    "description": rec.description,
                    "priority": rec.priority,
                    "target_coverage": rec.target_coverage,
                    "sequence_code": rec.sequence_code,
                    "has_code": bool(rec.sequence_code),
                }
                for rec in recs
            ],
        }

    except Exception as e:
        logger.error(f"Sequence recommendation failed: {e}", exc_info=True)
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════
# GET /api/coverage/protocols — Protocol coverage patterns
# ═══════════════════════════════════════════════════════════════

@router.get("/protocols")
async def coverage_protocols():
    """List protocol-specific coverage patterns VeriAssist can generate."""
    return {
        "protocols": [
            {
                "id": "axi",
                "name": "AXI4 / AXI4-Lite",
                "coverage_areas": [
                    "Write-read ordering",
                    "All BRESP/RRESP values",
                    "Back-to-back transactions",
                    "Ready-before-valid scenarios",
                    "Outstanding transaction counts",
                ],
            },
            {
                "id": "apb",
                "name": "APB",
                "coverage_areas": [
                    "Wait state counts (0, 1, 2, max)",
                    "PSLVERR assertion",
                    "Write/read alternation",
                    "Address range coverage",
                ],
            },
            {
                "id": "fifo",
                "name": "FIFO",
                "coverage_areas": [
                    "Fill levels (empty, 1, half, almost-full, full)",
                    "Simultaneous read/write",
                    "Overflow/underflow attempts",
                    "Fill-then-drain patterns",
                ],
            },
            {
                "id": "spi",
                "name": "SPI",
                "coverage_areas": [
                    "Data patterns (0x00, 0xFF, 0xAA, 0x55)",
                    "CPOL/CPHA mode combinations",
                    "Back-to-back transfers",
                ],
            },
            {
                "id": "fsm",
                "name": "FSM (any)",
                "coverage_areas": [
                    "State coverage (every state visited)",
                    "Transition coverage (every arc exercised)",
                    "Illegal state detection",
                    "Reset recovery path",
                    "Deadlock freedom",
                ],
            },
        ],
    }