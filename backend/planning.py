"""Illustrative RUB estimates; the demolition limit applies separately to each building."""
from math import ceil,hypot
from .data import apply_action
from .geo import project

PRICES={'add_stop':500_000,'add_park':2_000_000,'move_stop':150_000,'remove_stop':100_000,'remove_park':300_000,'close_edge':50_000,'open_edge':25_000}
LABELS={'add_stop':'Новая остановка','add_park':'Новая зелёная зона','move_stop':'Перенос остановки','demolish_building':'Снос здания','remove_stop':'Удаление остановки','remove_park':'Удаление парка','close_edge':'Перекрытие участка','open_edge':'Открытие участка'}
BUILDING_KINDS={'home','building','school','clinic','shop'}
CENTER=project(36.616,55.105)


def footprint_area(geom):
    if not geom:return None
    def ring_area(ring):
        points=[project(lon,lat) for lon,lat,*_ in ring]
        if len(points)<3:return 0
        return abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1])))/2
    polygons=[geom['coordinates']] if geom.get('type')=='Polygon' else geom.get('coordinates',[]) if geom.get('type')=='MultiPolygon' else []
    area=sum(max(0,ring_area(rings[0])-sum(ring_area(hole) for hole in rings[1:])) for rings in polygons if rings)
    return area if area>0 else None


def demolition_cost(obj):
    measured=footprint_area(obj.get('geom'));area=measured if measured is not None else 80
    residents=max(0,obj.get('residents',0));distance=hypot(obj['x']-CENTER[0],obj['y']-CENTER[1])
    factor=1+0.6*max(0,1-distance/4000)
    # Fixed works + footprint demolition + resident relocation allowance; centrality increases the estimate.
    amount=ceil((150_000+area*2500+residents*20_000)*factor/1000)*1000
    return dict(amount=amount,area_m2=round(area,1),area_estimated=measured is None,residents=residents,
                distance_to_center_m=round(distance),location_factor=round(factor,3))


def demolition_info(obj,limit):
    if obj['kind'] not in BUILDING_KINDS:return None
    detail=demolition_cost(obj);allowed=detail['amount']<=limit
    return dict(**detail,limit=limit,allowed=allowed,reason='' if allowed else f"Снос невозможен из-за цены: {detail['amount']:,} ₽ за здание выше порога {limit:,} ₽".replace(',',' '))


def annotate_costs(state):
    limit=state['demolition_policy']['limit']
    return {o['id']:demolition_info(o,limit) for o in state['objects'] if o['kind'] in BUILDING_KINDS}


def plan_changes(state,actions):
    current=state;lines=[];targets=set();limit=state['demolition_policy']['limit']
    for action in actions:
        key=(action['entity'],action['id'])
        if key in targets:raise ValueError('В наборе может быть только одно изменение каждого объекта или участка')
        targets.add(key);changed=apply_action(current,action)
        values=action.get('values',{});obj=next((o for o in current['objects'] if o['id']==action['id']),None)
        detail=None
        if action['entity']=='edge':code='close_edge' if values['closed'] else 'open_edge'
        elif action['operation']=='add':code='add_'+values['kind']
        elif action['operation']=='update':code='move_stop'
        else:
            code='remove_'+obj['kind'] if obj['kind'] in {'stop','park'} else 'demolish_building'
            if code=='demolish_building':detail=demolition_info(obj,limit)
        name=obj['name'] if obj else values.get('name','Пешеходный участок')
        lines.append(dict(id=action['id'],name=name,label=LABELS[code],amount=detail['amount'] if detail else PRICES[code],demolition=detail))
        current=changed
    blocked=[dict(id=l['id'],name=l['name'],**l['demolition']) for l in lines if l['demolition'] and not l['demolition']['allowed']]
    return current,dict(total=sum(l['amount'] for l in lines),limit=limit,can_submit=not blocked,blocked=blocked,lines=lines,
                        note='Учебная оценка, не рыночная смета. Порог действует на снос каждого здания отдельно. Общего бюджета и списания денег нет.')


def blocking_reason(estimate):
    return '; '.join(f"{b['name']}: {b['reason']}" for b in estimate['blocked'])
