from __future__ import annotations

import pytest

from voxcpm_wyomming.config import build_arg_parser, config_from_args


def test_config_from_args_parses_devices() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(["--model", "openbmb/VoxCPM2", "--devices", "0,2"])
    config = config_from_args(args)
    assert config.model == "openbmb/VoxCPM2"
    assert config.devices == (0, 2)
    assert config.uri == "tcp://0.0.0.0:10200"


def test_config_from_args_requires_model() -> None:
    parser = build_arg_parser()
    args = parser.parse_args([])
    with pytest.raises(ValueError, match="--model is required"):
        config_from_args(args)


def test_config_from_args_validates_gpu_memory_utilization() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(["--model", "m", "--gpu-memory-utilization", "0"])
    with pytest.raises(ValueError, match="gpu-memory-utilization"):
        config_from_args(args)


def test_config_from_args_validates_devices() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(["--model", "m", "--devices", "0,-1"])
    with pytest.raises(ValueError, match="non-negative"):
        config_from_args(args)


def test_config_from_args_validates_empty_devices() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(["--model", "m", "--devices", ",,,"])
    with pytest.raises(ValueError, match="devices list is empty"):
        config_from_args(args)


def test_config_from_args_validates_port_range() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(["--model", "m", "--port", "70000"])
    with pytest.raises(ValueError, match="--port"):
        config_from_args(args)


def test_config_from_args_validates_batch_limits() -> None:
    parser = build_arg_parser()

    args_tokens = parser.parse_args(["--model", "m", "--max-num-batched-tokens", "0"])
    with pytest.raises(ValueError, match="max-num-batched-tokens"):
        config_from_args(args_tokens)

    args_seqs = parser.parse_args(["--model", "m", "--max-num-seqs", "0"])
    with pytest.raises(ValueError, match="max-num-seqs"):
        config_from_args(args_seqs)
