# Copyright (c) 2026 DevRev Inc. All rights reserved.

import pytest

from scraper.adapters.reddit import is_housekeeping


@pytest.mark.parametrize(
    ("author", "title"),
    [
        ("/u/AutoModerator", "What are you working on?"),
        ("/u/BernardJOrtcutt", "/r/philosophy Open Discussion Thread | October 12, 2026"),
        ("/u/someone", "Weekly Discussion Thread"),
        ("/u/someone", "[Megathread] Spooky Season"),
        ("/u/someone", "Welcome to /r/askphilosophy! Check out our rules"),
        ("/u/someone", "Daily General Discussion and Advice Thread - October 16, 2026"),
        ("/u/someone", "Share your startup - quarterly post"),
        ("/u/someone", "Psychological Research/Surveys Thread"),
    ],
)
def test_moderator_posts_and_recurring_threads_are_skipped(author: str, title: str) -> None:
    assert is_housekeeping({"author": {"name": author}, "title": title})


@pytest.mark.parametrize(
    ("author", "title"),
    [
        ("/u/someone", "Got laid off from product designer post and now panicking"),
        ("/u/AskScienceModerator", "AskScience AMA Series: I'm a neuroengineering professor"),
        ("/u/someone", "How do I focus when doing creative work?"),
    ],
)
def test_real_posts_are_kept(author: str, title: str) -> None:
    assert not is_housekeeping({"author": {"name": author}, "title": title})
