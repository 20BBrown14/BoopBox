#pragma once

#ifdef USE_ESP32

#include <atomic>
#include <cstdint>

#include "esphome/components/speaker/speaker.h"
#include "esphome/core/component.h"

namespace esphome::balance {

/// Pass-through speaker that applies a left/right balance to 16-bit stereo audio
/// before handing it to the real output speaker. Any other format passes through
/// untouched. Volume, mute and pause are forwarded to the output speaker.
///
/// Balance law: the near side stays at full level and the far side fades out on a
/// quarter-cosine, so centre is exactly as loud as having no balance at all.
class BalanceSpeaker final : public Component, public speaker::Speaker {
 public:
  float get_setup_priority() const override { return setup_priority::DATA; }
  void setup() override;
  void loop() override;
  void dump_config() override;

  size_t play(const uint8_t *data, size_t length, TickType_t ticks_to_wait) override;
  size_t play(const uint8_t *data, size_t length) override { return this->play(data, length, 0); }

  void start() override;
  void stop() override;
  void finish() override;

  void set_pause_state(bool pause_state) override { this->output_speaker_->set_pause_state(pause_state); }
  bool get_pause_state() const override { return this->output_speaker_->get_pause_state(); }

  bool has_buffered_data() const override { return this->output_speaker_->has_buffered_data(); }

  void set_volume(float volume) override { this->output_speaker_->set_volume(volume); }
  float get_volume() override { return this->output_speaker_->get_volume(); }
  void set_mute_state(bool mute_state) override { this->output_speaker_->set_mute_state(mute_state); }
  bool get_mute_state() override { return this->output_speaker_->get_mute_state(); }

  void set_output_speaker(speaker::Speaker *speaker) { this->output_speaker_ = speaker; }

  /// @param balance -1.0 (left only) .. 0 (centre) .. +1.0 (right only). Safe to call any time.
  void set_balance(float balance);
  float get_balance() const { return this->balance_; }

 protected:
  void sync_state_();

  static constexpr size_t SCRATCH_BYTES = 2048;

  speaker::Speaker *output_speaker_{nullptr};
  uint8_t scratch_[SCRATCH_BYTES];

  float balance_{0.0f};
  // Q15 gains (32768 = unity). Written from the main loop, read in the audio task.
  std::atomic<int32_t> gain_left_{32768};
  std::atomic<int32_t> gain_right_{32768};

  // The output can accept a partial count of bytes, so track where in the stereo
  // frame (0..3) the next incoming byte falls, and keep the original low byte of a
  // sample whose high byte hasn't been accepted yet.
  uint8_t phase_{0};
  uint8_t carry_low_{0};
};

}  // namespace esphome::balance

#endif
