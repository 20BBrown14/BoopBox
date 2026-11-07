"""Balance: a pass-through speaker that applies a left/right balance to 16-bit stereo audio."""

import esphome.codegen as cg

CODEOWNERS = ["@hvilander"]

balance_ns = cg.esphome_ns.namespace("balance")
