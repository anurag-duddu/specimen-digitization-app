"""Sanitize provider exceptions before agent instrumentation can record bodies."""

from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models.instrumented import InstrumentationSettings
from pydantic_ai.models.wrapper import WrapperModel


class PrivateProviderModel(WrapperModel):
    async def request(self, messages, model_settings, model_request_parameters):
        try:
            return await self.wrapped.request(
                messages, model_settings, model_request_parameters
            )
        except ModelHTTPError as exc:
            raise ModelHTTPError(
                exc.status_code, self.model_name, "provider_request_failed"
            ) from None
        except TimeoutError:
            raise TimeoutError("provider_request_timeout") from None
        except Exception:
            raise RuntimeError("provider_request_failed") from None


def agent_instrumentation():
    """An agent's instrumentation, following the process's capture mode.

    System prompts, messages and tool calls only in the approved-content mode
    (LANE.md T5b, PLAN 4.5, G3); binary content never. With nothing
    configured, the metadata mode applies. Provider errors stay sanitized by
    PrivateProviderModel either way.
    """
    from .observability import configured_capture_mode, CaptureMode

    content = configured_capture_mode() is CaptureMode.APPROVED_CONTENT
    return InstrumentationSettings(
        include_content=content,
        include_binary_content=False,
        include_model_request_parameters=content,
    )
