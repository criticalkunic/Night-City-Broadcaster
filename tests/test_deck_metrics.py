from types import SimpleNamespace
from app.deck_metrics import metrics


def test_copy_weighted_metrics_separate_legends_and_unknown_costs():
    cards={
      'a':{'card_type':'Unit','color':'Red','cost':2,'classifications':['Merc','Merc']},
      'b':{'card_type':'Program','color':'Blue','cost':0,'classifications':['Merc','Braindance']},
      'c':{'card_type':'Gear','color':'Blue','cost':None,'classifications':[]},
      'l':{'card_type':'Legend','color':'Green','cost':9,'classifications':['Legend tag']},
    }
    entries=[SimpleNamespace(card_id=cid,quantity=n) for cid,n in [('a',3),('b',2),('c',1),('l',1),('missing',1)]]
    result=metrics(entries,cards)
    assert result['total']==6 and result['legends']==1 and result['missing']==1
    assert result['average_cost']==1.2 and result['unknown_cost']==1
    assert result['tags'][0]=={'label':'Merc','count':5,'colors':{'Red':3,'Blue':2}}
    assert [r['label'] for r in result['curve']]==['0','2','Unknown']
    assert sum(r['count'] for r in result['types'])==6
    assert result['colors']=={'Red':3,'Blue':3}


def test_top_five_deterministic_and_empty_deck():
    assert metrics([], {})['average_cost'] is None
    result=metrics([SimpleNamespace(card_id='a',quantity=1)],{'a':{'classifications':['Z','F','E','D','C','B','A'],'color':['Red','Blue'],'cost':'X'}})
    assert [r['label'] for r in result['tags']]==list('ABCDE')
    assert result['colors']=={'Blue / Red':1}


def test_filters_recalculate_denominators_and_sort():
    cards={'a':{'card_type':'Unit','color':'Red','cost':5,'classifications':['Merc']},
           'b':{'card_type':'Unit','color':'Blue','cost':1,'classifications':['Merc']},
           'c':{'card_type':'Gear','color':'Red','cost':2,'classifications':['Cyberware']}}
    entries=[SimpleNamespace(card_id=k,quantity=q) for k,q in [('a',3),('b',2),('c',1)]]
    filtered=metrics(entries,cards,{'color':'Red','card_type':'Unit'})
    assert filtered['total']==3 and filtered['average_cost']==5
    assert filtered['colors']=={'Red':3}
    assert filtered['available_colors']==['Blue','Red']
    assert filtered['available_types']==['Gear','Unit']
    sorted_rows=metrics(entries,cards,{'sort':'count_desc'})['curve']
    assert [r['label'] for r in sorted_rows]==['5','1','2']
    assert metrics(entries,cards,{'color':'Yellow'})['total']==0


def test_tag_limit_and_alphabetic_sort():
    entries=[SimpleNamespace(card_id='a',quantity=1)]
    cards={'a':{'classifications':list('ABCDEFGHIJK')}}
    assert len(metrics(entries,cards,{'tag_limit':10,'sort':'name'})['tags'])==10
