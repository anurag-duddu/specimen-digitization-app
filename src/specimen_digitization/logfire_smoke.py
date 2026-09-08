"""Send one synthetic Pydantic AI run to verify Logfire configuration."""

from __future__ import annotations

import argparse

import logfire
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from specimen_digitization.observability import configure_observability


def run_synthetic_harness() -> str:
    """Exercise agent instrumentation without external model credentials."""
    agent = Agent(
        TestModel(),
        instructions="Return a deterministic result for an observability check.",
    )
    with logfire.span(
        "Run synthetic specimen harness smoke",
        run_kind="synthetic",
    ):
        result = agent.run_sync("Verify the specimen harness telemetry path.")
        logfire.info(
            "Completed synthetic specimen harness smoke",
            run_kind="synthetic",
            outcome="success",
        )
    return result.output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-send",
        action="store_true",
        help="Exercise the integration without exporting telemetry.",
    )
    args = parser.parse_args()

    configure_observability(send_to_logfire=False if args.no_send else None)
    run_synthetic_harness()
    logfire.force_flush()
    print("Synthetic Pydantic AI observability check completed.")


if __name__ == "__main__":
    main()
