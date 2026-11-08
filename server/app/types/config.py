from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class StreamingMode(StrEnum):
    proxy = "proxy"
    redirect = "redirect"  # not yet functional


class MappingKind(StrEnum):
    item = "item"
    collection = "collection"


class SourceConfig(BaseModel):
    id: str
    type: str
    base_url: str
    user_id: str | None = None


class MappingEntry(BaseModel):
    source: str
    item: str
    kind: MappingKind = MappingKind.item


class StreamingConfig(BaseModel):
    mode: StreamingMode = StreamingMode.proxy
    pause_budget_seconds: int = 1800


class OtaConfig(BaseModel):
    manifest_version: str = "0.1.0"
    # Gates the auto-push-on-publish trigger. Default off so an upload is
    # inert until an operator explicitly enables fleet pushes.
    auto_push_on_publish: bool = False


class FileConfig(BaseModel):
    """The validated contents of config.yaml."""

    sources: list[SourceConfig] = Field(default_factory=list)
    mappings: dict[str, list[MappingEntry]] = Field(default_factory=dict)
    streaming: StreamingConfig = Field(default_factory=StreamingConfig)
    ota: OtaConfig = Field(default_factory=OtaConfig)

    @model_validator(mode="after")
    def _mappings_reference_known_sources(self) -> "FileConfig":
        known = {s.id for s in self.sources}
        for slug, entries in self.mappings.items():
            for entry in entries:
                if entry.source not in known:
                    raise ValueError(
                        f"mapping '{slug}' references undefined source id "
                        f"'{entry.source}'"
                    )
        return self
