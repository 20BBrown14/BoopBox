#include "balance_speaker.h"

#ifdef USE_ESP32

#include <algorithm>
#include <cmath>

#include "esphome/core/log.h"

namespace esphome::balance {

static const char *const TAG = "balance";

void BalanceSpeaker::setup() {
  // Pass through playback-position callbacks from the real speaker.
  this->output_speaker_->add_audio_output_callback(
      [this](uint32_t frames, int64_t timestamp) { this->audio_output_callback_.call(frames, timestamp); });
}

void BalanceSpeaker::dump_config() {
  ESP_LOGCONFIG(TAG,
                "Balance Speaker:\n"
                "  Balance: %.2f",
                this->balance_);
}

void BalanceSpeaker::loop() { this->sync_state_(); }

// The media pipeline polls is_running() (non-virtual, reads state_) to know when
// playback has finished, so mirror the output speaker's state.
void BalanceSpeaker::sync_state_() {
  if (this->output_speaker_->is_running()) {
    this->state_ = speaker::STATE_RUNNING;
  } else if (this->output_speaker_->is_stopped()) {
    this->state_ = speaker::STATE_STOPPED;
  }
}

void BalanceSpeaker::set_balance(float balance) {
  balance = std::clamp(balance, -1.0f, 1.0f);
  this->balance_ = balance;
  float far = std::cos(std::fabs(balance) * static_cast<float>(M_PI) / 2.0f);
  int32_t far_q15 = static_cast<int32_t>(std::lround(far * 32768.0f));
  this->gain_left_.store(balance > 0.0f ? far_q15 : 32768);
  this->gain_right_.store(balance < 0.0f ? far_q15 : 32768);
  ESP_LOGD(TAG, "Balance %.2f (L %ld, R %ld of 32768)", balance, (long) this->gain_left_.load(),
           (long) this->gain_right_.load());
}

void BalanceSpeaker::start() {
  this->phase_ = 0;
  this->output_speaker_->set_audio_stream_info(this->audio_stream_info_);
  this->output_speaker_->start();
  this->state_ = speaker::STATE_STARTING;
}

void BalanceSpeaker::stop() {
  this->output_speaker_->stop();
  this->state_ = speaker::STATE_STOPPING;
}

void BalanceSpeaker::finish() {
  this->output_speaker_->finish();
  this->state_ = speaker::STATE_STOPPING;
}

static inline int16_t scale_sample(int16_t sample, int32_t gain_q15) {
  return static_cast<int16_t>((static_cast<int32_t>(sample) * gain_q15) >> 15);
}

size_t BalanceSpeaker::play(const uint8_t *data, size_t length, TickType_t ticks_to_wait) {
  if (this->state_ != speaker::STATE_RUNNING && this->state_ != speaker::STATE_STARTING) {
    this->start();
  }

  const auto &info = this->audio_stream_info_;
  if (info.get_bits_per_sample() != 16 || info.get_channels() != 2) {
    // Only 16-bit stereo is balanced; pass anything else straight through.
    size_t written = this->output_speaker_->play(data, length, ticks_to_wait);
    this->sync_state_();
    return written;
  }

  const int32_t gains[2] = {this->gain_left_.load(), this->gain_right_.load()};

  // Process at most one scratch buffer, and end on a whole sample so every byte we
  // hand out was computed from a complete sample.
  size_t n = std::min(length, SCRATCH_BYTES);
  if ((this->phase_ + n) & 1)
    n--;
  if (n == 0)
    return 0;

  size_t i = 0;
  uint8_t pos = this->phase_;
  if (pos & 1) {
    // Starts on the high byte of a sample whose low byte was already accepted.
    int16_t s = static_cast<int16_t>(this->carry_low_ | (data[0] << 8));
    int16_t v = scale_sample(s, gains[pos >> 1]);
    this->scratch_[0] = static_cast<uint8_t>(static_cast<uint16_t>(v) >> 8);
    i = 1;
    pos = (pos + 1) & 3;
  }
  // n - i is even here, so the loop always reads whole samples.
  for (; i < n; i += 2) {
    int16_t s = static_cast<int16_t>(data[i] | (data[i + 1] << 8));
    int16_t v = scale_sample(s, gains[pos >> 1]);
    this->scratch_[i] = static_cast<uint8_t>(static_cast<uint16_t>(v) & 0xFF);
    this->scratch_[i + 1] = static_cast<uint8_t>(static_cast<uint16_t>(v) >> 8);
    pos = (pos + 2) & 3;
  }

  size_t written = this->output_speaker_->play(this->scratch_, n, ticks_to_wait);
  if (written > 0) {
    uint8_t new_phase = (this->phase_ + written) & 3;
    if (new_phase & 1) {
      // Stopped right after a low byte: keep the original so the next call can
      // rebuild this sample.
      this->carry_low_ = data[written - 1];
    }
    this->phase_ = new_phase;
  }
  this->sync_state_();
  return written;
}

}  // namespace esphome::balance

#endif
