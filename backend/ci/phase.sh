#!/usr/bin/env bash
# Explicitly return the pipeline's result even when the caller uses an if statement.
phase() {
  local name=$1 result=0; shift
  echo "::group::$name"
  "$@" 2>&1 | tee "$reports/$name.log" || result=$?
  echo '::endgroup::'
  return "$result"
}
