from types import SimpleNamespace

from app.vision.play_tracker import PlayTracker


def detection(x, y=.5):
    return SimpleNamespace(center=(x,y))


def match(name):
    return SimpleNamespace(card_id=name)


def test_every_stable_candidate_is_checked_even_if_first_is_wrong():
    tracker=PlayTracker()
    cards=[detection(.2), detection(.5), detection(.8)]
    for tick in range(5):
        tracker.update(cards,tick*.1)
    checked=[]
    for now in [.5,.6,.7]:
        track=tracker.next_check(now,5)
        checked.append(track['id'])
        track['checked']=now
    assert checked == [1,2,3]


def test_moving_card_and_replacement_do_not_depend_on_new_location():
    tracker=PlayTracker()
    tracker.update([detection(.2)],0)
    first=tracker.tracks[0]
    assert tracker.accept(first,match('A'),0)
    tracker.update([detection(.7)],.1)
    moved=tracker.tracks[-1]
    # Identity recognition remains possible anywhere, even across the ROI.
    tracker.accept(moved,match('A'),.1)
    assert tracker.latest_id=='A'
    assert tracker.accept(moved,match('B'),.2)
    assert tracker.latest_id=='B'
    assert not tracker.accept(moved,match('B'),.3)


def test_other_visible_cards_cannot_block_latest_removal():
    tracker=PlayTracker()
    a,b=detection(.2),detection(.7)
    tracker.update([a,b],0)
    tracker.accept(tracker.tracks[0],match('A'),0)
    tracker.accept(tracker.tracks[1],match('B'),0)
    for now in [1,1.4,1.8,2.2]:
        tracker.update([a],now)
        assert not tracker.removed(now,1.5,5)
    tracker.update([a],2.6)
    assert tracker.removed(2.6,1.5,5)
    assert tracker.latest_id is None


def test_brief_contour_dropout_does_not_restart_stability():
    tracker=PlayTracker()
    for tick in range(4): tracker.update([detection(.5)],tick*.1)
    tracker.update([],.4)
    tracker.update([detection(.5)],.5)
    assert tracker.next_check(.5,5) is not None
