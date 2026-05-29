"""Tests for the playback decision logic.

The decision function (player module) is pure — it takes a current_playback()
response shape and config flags, and returns whether to start playback. These
tests mock spotipy responses; they never hit the network.

Cases to cover:
    - nothing playing            -> start
    - actively playing           -> do nothing
    - paused, paused_counts=True  -> do nothing
    - paused, paused_counts=False -> start
    - no active device (None)    -> start (triggers launch fallback)
"""

import pytest

pytest.skip("scaffold — decision logic not implemented yet", allow_module_level=True)
