"""The polling loop, error handling, and logging.

Polls playback every poll_interval seconds. Transient API/network errors are
logged and the loop continues rather than killing the process. Logging is to a
rotating file so autostart/headless runs are debuggable.
"""
