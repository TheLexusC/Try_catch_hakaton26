import test from 'node:test';
import assert from 'node:assert/strict';
import {phaseForYear,milestoneForYear,relatedBuildings,streetFeatures,directions,strategySource} from './strategy.js';
test('2025–2040 years follow section 4.1, excluding the superseded source',()=>{
  for(const y of [2025,2026,2027])assert.equal(phaseForYear(y).id,1);
  for(const y of [2028,2030,2033])assert.equal(phaseForYear(y).id,2);
  for(const y of [2034,2037,2040])assert.equal(phaseForYear(y).id,3);
  assert.equal(phaseForYear(2019),undefined);
  assert.ok(strategySource.decision.includes('01-49'));
  assert.ok(strategySource.decrees.some(d=>d.number===145));
  assert.ok(directions.every(d=>d.startYear===undefined));
});
test('appendix Д forecast figures are not interpolated or confused with 2018 housing targets',()=>{
  assert.deepEqual(milestoneForYear(2025),{year:2027,population:137900,employment:50700,investment:14.5});
  assert.deepEqual(milestoneForYear(2030),{year:2033,population:143100,employment:53700,investment:19.5});
  assert.equal(milestoneForYear(2040).population,148000);
  assert.equal(milestoneForYear(2040).investment,26.2);
  assert.equal(milestoneForYear(2022),null);
});
test('document-related addresses and museum are distinguished from other current buildings',()=>{
  const objects=[{id:'a',kind:'home',name:'проспект Ленина, 20'},{id:'b',kind:'building',name:'Университетская улица, 50'},{id:'c',kind:'home',name:'улица Курчатова, 17'},{id:'b35153731',kind:'building',name:'проспект Ленина, 128'},{id:'d',kind:'stop',name:'Университетская улица'}];
  assert.deepEqual(relatedBuildings(objects,'campus').map(o=>o.id),['b']);
  assert.deepEqual(relatedBuildings(objects,'tourism').map(o=>o.id),['b35153731']);
  assert.deepEqual(relatedBuildings(objects,'ecology'),[]);
  assert.equal(objects.length,5);
});
test('map overlays use OSM geometry, preserve source, and omit unknown project boundaries',()=>{
  const features=[{properties:{name:'Университетская улица',kind:'road'},geometry:{type:'LineString',coordinates:[[36.6,55.1],[36.61,55.11]]}},{properties:{name:'Университетская улица',kind:'green'},geometry:{type:'Polygon',coordinates:[]}}];
  assert.equal(streetFeatures({features},'campus').length,1);
  assert.equal(streetFeatures({features},'utilities').length,0);
  assert.ok(streetFeatures({features},'protva').length>0);
  assert.equal(features[0].properties.planTitle,undefined);
});
