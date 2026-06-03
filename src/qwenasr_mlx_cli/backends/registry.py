from qwenasr_mlx_cli.backends.mlx_backend import MLXBackend
from qwenasr_mlx_cli.core.exceptions import BackendUnavailableError


class BackendRegistry:
    def __init__(self) -> None:
        self._factories = {
            "mlx": MLXBackend,
        }

    def names(self) -> list[str]:
        return sorted(self._factories)

    def create(self, name: str):
        try:
            backend = self._factories[name]()
        except KeyError as exc:
            raise BackendUnavailableError(f"Unknown backend: {name}") from exc
        return backend
