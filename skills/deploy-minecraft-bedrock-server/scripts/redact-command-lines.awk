function is_sensitive_flag(value, normalized) {
  normalized = tolower(value)
  sub(/^--?/, "", normalized)
  sub(/=.*/, "", normalized)
  return normalized ~ /^(token|password|passwd|secret|api[-_]?key|auth|access[-_]?token)$/
}

{
  redact_next = 0
  for (i = 1; i <= NF; i++) {
    lowered = tolower($i)
    if (redact_next) {
      $i = "[REDACTED]"
      redact_next = 0
    } else if (lowered ~ /^https?:\/\//) {
      $i = "[REDACTED_URL]"
    } else if (is_sensitive_flag($i)) {
      if (index($i, "=") > 0) sub(/=.*/, "=[REDACTED]", $i)
      else redact_next = 1
    } else if (lowered == "bearer") {
      redact_next = 1
    }
  }
  print
}
