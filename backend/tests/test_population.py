from backend.seed import seed_state

def test_original_city_is_exactly_133000_conditional_residents():
    state=seed_state()
    homes=[o for o in state['objects'] if o['kind']=='home']
    assert sum(h['residents'] for h in homes)==133000
    assert all(isinstance(h['residents'],int) and h['residents']>=0 for h in homes)
    assert [(h['id'],h['residents']) for h in homes]==[(h['id'],h['residents']) for h in seed_state()['objects'] if h['kind']=='home']
