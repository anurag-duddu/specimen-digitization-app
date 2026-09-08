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
