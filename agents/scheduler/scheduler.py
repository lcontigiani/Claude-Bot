"""
Scheduler: Ejecuta los agentes en intervalos configurados usando APScheduler.
"""

import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import agent_config as cfg

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor

logger = logging.getLogger("scheduler")


def build_scheduler(agents: dict) -> BackgroundScheduler:
    """
    Construye y configura el scheduler con todos los agentes.

    Args:
        agents: dict con claves: 'system_monitor', 'code_analyst',
                'data_reporter', 'improvement_proposer', 'orchestrator'
    Returns:
        BackgroundScheduler listo para iniciar
    """
    executors = {"default": ThreadPoolExecutor(max_workers=5)}
    job_defaults = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 60}

    scheduler = BackgroundScheduler(
        executors=executors,
        job_defaults=job_defaults,
        timezone=cfg.SCHEDULER_TIMEZONE,
    )

    # --- System Monitor: cada 5 minutos ---
    if "system_monitor" in agents:
        scheduler.add_job(
            func=agents["system_monitor"].run,
            trigger="interval",
            minutes=5,
            jitter=15,
            id="system_monitor",
            name="System Monitor",
        )
        logger.info("Job registrado: system_monitor (cada 5 min)")

    # --- Orchestrator: cada 10 minutos ---
    if "orchestrator" in agents:
        scheduler.add_job(
            func=agents["orchestrator"].run,
            trigger="interval",
            minutes=10,
            jitter=20,
            id="orchestrator",
            name="Orchestrator",
        )
        logger.info("Job registrado: orchestrator (cada 10 min)")

    # --- Code Analyst: cada 30 minutos ---
    if "code_analyst" in agents:
        scheduler.add_job(
            func=agents["code_analyst"].run,
            trigger="interval",
            minutes=30,
            jitter=30,
            id="code_analyst",
            name="Code Analyst",
        )
        logger.info("Job registrado: code_analyst (cada 30 min)")

    # --- Improvement Proposer: cada 45 minutos ---
    if "improvement_proposer" in agents:
        scheduler.add_job(
            func=agents["improvement_proposer"].run,
            trigger="interval",
            minutes=45,
            jitter=30,
            id="improvement_proposer",
            name="Improvement Proposer",
        )
        logger.info("Job registrado: improvement_proposer (cada 45 min)")

    # --- Data Reporter: cada 60 minutos ---
    if "data_reporter" in agents:
        scheduler.add_job(
            func=agents["data_reporter"].run,
            trigger="interval",
            minutes=60,
            jitter=60,
            id="data_reporter",
            name="Data Reporter",
        )
        logger.info("Job registrado: data_reporter (cada 60 min)")

    return scheduler
