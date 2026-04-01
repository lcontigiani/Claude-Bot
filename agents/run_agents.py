"""
Punto de entrada del sistema multi-agente.
Inicializa DB, instancia agentes, arranca scheduler y dashboard.
Expone controles de pausa/reanudacion/shutdown via el dashboard.
"""

import sys
import os
import time
import threading
import logging

# Asegurar que el path incluye la carpeta agents/
sys.path.insert(0, os.path.dirname(__file__))

import agent_config as cfg
from core import memory
from agents.system_monitor       import SystemMonitorAgent
from agents.code_analyst         import CodeAnalystAgent
from agents.data_reporter        import DataReporterAgent
from agents.improvement_proposer import ImprovementProposerAgent
from agents.orchestrator         import OrchestratorAgent
from scheduler.scheduler         import build_scheduler
from dashboard.dashboard_server  import run_dashboard, set_scheduler_ref, set_agents_ref

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)-22s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("run_agents")


def main():
    print("=" * 55)
    print("   SISTEMA MULTI-AGENTE - Iniciando")
    print("=" * 55)

    # 1. Inicializar base de datos
    logger.info("Inicializando base de datos...")
    memory.init_db()
    logger.info(f"DB: {cfg.DB_PATH}")

    # 2. Instanciar agentes
    logger.info("Instanciando agentes...")
    monitor    = SystemMonitorAgent()
    analyst    = CodeAnalystAgent()
    reporter   = DataReporterAgent()
    proposer   = ImprovementProposerAgent()
    orchestr   = OrchestratorAgent()

    agents = {
        "system_monitor":       monitor,
        "code_analyst":         analyst,
        "data_reporter":        reporter,
        "improvement_proposer": proposer,
        "orchestrator":         orchestr,
    }

    # El orquestador necesita conocer a los demas para dispararlos
    orchestr.set_registry(agents)

    # 3. Ejecutar primer ciclo inmediato en background
    logger.info("Ejecutando primer ciclo de agentes...")
    def first_run():
        time.sleep(2)
        logger.info(">>> Primer run: System Monitor")
        monitor.run(triggered_by="startup")
        time.sleep(3)
        logger.info(">>> Primer run: Data Reporter")
        reporter.run(triggered_by="startup")
        time.sleep(3)
        logger.info(">>> Primer run: Code Analyst")
        analyst.run(triggered_by="startup")
        time.sleep(5)
        logger.info(">>> Primer run: Improvement Proposer")
        proposer.run(triggered_by="startup")
        time.sleep(3)
        logger.info(">>> Primer run: Orchestrator")
        orchestr.run(triggered_by="startup")

    threading.Thread(target=first_run, daemon=True).start()

    # 4. Arrancar scheduler
    logger.info("Iniciando scheduler...")
    scheduler = build_scheduler(agents)
    scheduler.start()
    logger.info("Scheduler activo.")

    # 5. Pasar referencias al dashboard para los controles
    set_scheduler_ref(scheduler)
    set_agents_ref(agents)

    # 6. Arrancar dashboard en thread separado
    logger.info(f"Iniciando dashboard en http://127.0.0.1:{cfg.DASHBOARD_PORT}")
    dash_thread = threading.Thread(target=run_dashboard, daemon=True)
    dash_thread.start()

    print()
    print(f"  Dashboard:  http://127.0.0.1:{cfg.DASHBOARD_PORT}")
    print(f"  Chatbot:    http://127.0.0.1:5050")
    print(f"  DB:         {cfg.DB_PATH}")
    print()
    print("  Presiona Ctrl+C para detener.")
    print("=" * 55)

    # 7. Mantener el proceso vivo
    try:
        while True:
            time.sleep(30)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Deteniendo sistema...")
        scheduler.shutdown(wait=False)
        logger.info("Sistema detenido.")


if __name__ == "__main__":
    main()
