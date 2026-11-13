"""Phase 0/1 ResourceManager tests: RAM/VRAM thresholds, bounded history, and admission gates."""

from core.config import ResourceLimits
from core.models import ResourceStatus
from core.resource_manager import ResourceManager, SimulationOverrides


def test_resource_manager_bounded_history() -> None:
    limits = ResourceLimits(monitor_history_maxlen=15)
    with ResourceManager(limits=limits) as rm:
        for _ in range(40):
            snap = rm.sample()
            assert snap.system_ram_total_mb > 0
            assert snap.main_ram_mb > 0
        assert len(rm.history) == 15


def test_low_ram_thresholds_refuse_and_trigger_emergency_stop() -> None:
    with ResourceManager() as rm:
        # < 3GB available RAM refuses new AI job
        rm.set_simulation_overrides(
            SimulationOverrides(
                system_ram_available_mb=2500.0,
                system_ram_total_mb=16384.0,
                vram_total_mb=8192.0,
                vram_free_mb=6500.0,
                gpu_name="NVIDIA GeForce RTX 5060 Ti",
            )
        )
        snap = rm.sample()
        assert snap.status == ResourceStatus.CRITICAL
        allowed, reason = rm.can_start_ai_job("2stem", require_gpu=True, gpu_ai_ready=True)
        assert allowed is False
        assert "RAM" in reason
        stop, _ = rm.should_emergency_stop_ai(snap)
        assert stop is False  # 2500MB >= 2048MB critical threshold

        # < 2GB available RAM triggers emergency stop
        rm.set_simulation_overrides(
            SimulationOverrides(
                system_ram_available_mb=1800.0,
                system_ram_total_mb=16384.0,
                vram_total_mb=8192.0,
                vram_free_mb=6500.0,
            )
        )
        snap_crit = rm.sample()
        assert snap_crit.status == ResourceStatus.CRITICAL
        stop, stop_reason = rm.should_emergency_stop_ai(snap_crit)
        assert stop is True
        assert "1800" in stop_reason


def test_8gb_vram_thresholds_for_2stem_and_4stem() -> None:
    with ResourceManager() as rm:
        # 3.5 GB free VRAM: neither 2-stem nor 4-stem allowed on GPU
        rm.set_simulation_overrides(
            SimulationOverrides(
                system_ram_available_mb=8192.0,
                vram_total_mb=8192.0,
                vram_free_mb=3500.0,
                gpu_name="NVIDIA GeForce RTX 5060 Ti",
            )
        )
        ok_2, _ = rm.can_start_ai_job("2stem", require_gpu=True, gpu_ai_ready=True)
        ok_4, _ = rm.can_start_ai_job("4stem", require_gpu=True, gpu_ai_ready=True)
        assert ok_2 is False
        assert ok_4 is False

        # 4.8 GB free VRAM: 2-stem allowed, 4-stem blocked
        rm.set_simulation_overrides(
            SimulationOverrides(
                system_ram_available_mb=8192.0,
                vram_total_mb=8192.0,
                vram_free_mb=4800.0,
                gpu_name="NVIDIA GeForce RTX 5060 Ti",
            )
        )
        ok_2, _ = rm.can_start_ai_job("2stem", require_gpu=True, gpu_ai_ready=True)
        ok_4, _ = rm.can_start_ai_job("4stem", require_gpu=True, gpu_ai_ready=True)
        assert ok_2 is True
        assert ok_4 is False

        # 6.2 GB free VRAM: both allowed, unless gpu_ai_ready=False or concurrent job exists
        rm.set_simulation_overrides(
            SimulationOverrides(
                system_ram_available_mb=8192.0,
                vram_total_mb=8192.0,
                vram_free_mb=6200.0,
                gpu_name="NVIDIA GeForce RTX 5060 Ti",
            )
        )
        ok_blocked, reason = rm.can_start_ai_job(
            "2stem", require_gpu=True, gpu_ai_ready=False, gpu_block_reason="no sm_120"
        )
        assert ok_blocked is False
        assert "sm_120" in reason

        rm.update_runtime_state(active_ai_jobs=1, loaded_models=1, current_model="mdx_low")
        ok_busy, busy_reason = rm.can_start_ai_job("2stem", require_gpu=True, gpu_ai_ready=True)
        assert ok_busy is False
        assert "并行" in busy_reason
