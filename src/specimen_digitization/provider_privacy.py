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


def private_instrumentation():
    return InstrumentationSettings(
        include_content=False,
        include_binary_content=False,
        include_model_request_parameters=False,
    )


def approved_content_configured() -> bool:
    """Whether this process's Logfire was configured for approved-content.

    It reads the settings configure_observability recorded, not the environment:
    an unconfigured process, or one configured for metadata (the bounded export
    path included), is metadata.
    """
    from . import observability

    settings = observability._configured_settings
    return settings is not None and settings.include_content


def agent_instrumentation():
    """Agent instrumentation that follows the process's configured capture mode.

    Under approved-content the system prompt, messages, tool calls and request
    parameters are recorded (G3); otherwise it records what private_instrumentation
    records. Binary content (image bytes) is never recorded. Provider error bodies
    are kept out by the model wrappers (PrivateProviderModel, the classifier's
    _CaptureModel), not by these settings.
    """
    content = approved_content_configured()
    return InstrumentationSettings(
        include_content=content,
        include_binary_content=False,
        include_model_request_parameters=content,
        version=5,
    )
