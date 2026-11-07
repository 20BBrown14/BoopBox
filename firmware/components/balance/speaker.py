import esphome.codegen as cg
from esphome.components import speaker
import esphome.config_validation as cv
from esphome.const import (
    CONF_BITS_PER_SAMPLE,
    CONF_ID,
    CONF_NUM_CHANNELS,
    CONF_OUTPUT_SPEAKER,
    CONF_SAMPLE_RATE,
    PLATFORM_ESP32,
)
from esphome.core.entity_helpers import inherit_property_from

from . import balance_ns

AUTO_LOAD = ["audio"]
DEPENDENCIES = ["speaker"]

BalanceSpeaker = balance_ns.class_("BalanceSpeaker", cg.Component, speaker.Speaker)

CONF_BALANCE = "balance"

CONFIG_SCHEMA = cv.All(
    speaker.SPEAKER_SCHEMA.extend(
        {
            cv.GenerateID(): cv.declare_id(BalanceSpeaker),
            cv.Required(CONF_OUTPUT_SPEAKER): cv.use_id(speaker.Speaker),
            # -1.0 = left only, 0 = centre, +1.0 = right only
            cv.Optional(CONF_BALANCE, default=0.0): cv.float_range(min=-1.0, max=1.0),
        }
    ).extend(cv.COMPONENT_SCHEMA),
    cv.only_on([PLATFORM_ESP32]),
)


def _inherit_from_output(config):
    # The media player reads the stream format from this speaker's config, so it
    # must look exactly like the speaker it wraps.
    for prop in (CONF_NUM_CHANNELS, CONF_SAMPLE_RATE, CONF_BITS_PER_SAMPLE):
        inherit_property_from(prop, CONF_OUTPUT_SPEAKER)(config)
    return config


FINAL_VALIDATE_SCHEMA = _inherit_from_output


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await speaker.register_speaker(var, config)

    output_spkr = await cg.get_variable(config[CONF_OUTPUT_SPEAKER])
    cg.add(var.set_output_speaker(output_spkr))
    cg.add(var.set_balance(config[CONF_BALANCE]))
