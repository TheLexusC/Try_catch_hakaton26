// Source: user-supplied Strategiya 25-40(4)(1).doc, sections 3.3–3.4, 4.1 and appendix Д.
// Stage deadlines are documented; individual building dates and project boundaries are not.
import extraGeometry from './strategyGeometry.js';
export const strategySource={
  title:'Стратегия Обнинска как наукограда РФ на 2025–2040 годы',
  decision:'Решение Обнинского городского Собрания от 30.01.2024 № 01-49',
  original:'Предоставленный документ: «Strategiya 25-40(4)(1).doc», Обнинск, 2024',
  url:'https://www.obninsk.ru/obninsk/economic-development/strategia-plan/strategy2025-40/',
  file:'/documents/obninsk-strategy-2025-2040.doc',
  decrees:[{number:821,date:'06.05.2000',title:'О присвоении статуса наукограда Российской Федерации г. Обнинску Калужской области'},
    {number:400,date:'02.07.2021',title:'О Стратегии национальной безопасности Российской Федерации'},
    {number:145,date:'28.02.2024',title:'О Стратегии научно-технологического развития Российской Федерации'},
    {number:490,date:'10.10.2019',title:'О развитии искусственного интеллекта в Российской Федерации'}]
};
export const phases=[
  {id:1,start:2025,end:2027,color:'#a47417',title:'Первоочередные мероприятия и выбор проектов',description:'Формирование институциональных структур, инфраструктурные и другие первоочередные мероприятия, выбор ключевых проектов и уточнение второй очереди.'},
  {id:2,start:2028,end:2033,color:'#197bc0',title:'Основная инфраструктура и запуск обновлённых систем',description:'Завершение строительства и реконструкции основных инфраструктурных объектов, запуск обновлённой образовательной системы, внедрение инноваций в городские сервисы.'},
  {id:3,start:2034,end:2040,color:'#7659b4',title:'Развитие проектов и достижение целей',description:'Развитие ключевых проектов второй очереди, синхронизация науки, производства, образования и городских сервисов, выполнение показателей и анализ результатов.'}
];
// Appendix Д: figures for each milestone year, not cumulative spending.
export const targets={
  2027:{population:137900,employment:50700,investment:14.5},
  2033:{population:143100,employment:53700,investment:19.5},
  2040:{population:148000,employment:57500,investment:26.2}
};
export const directions=[
  {id:'housing',title:'Жилая застройка на продолжении проспекта Ленина',section:'Раздел 3.4',streets:['Ленина'],description:'Развитие жилой застройки в северо-западном направлении на продолжении проспекта Ленина в синхронизации с Генеральным планом.',location:'Существующий проспект — ориентир. Местоположение новых домов и границы застройки в этом документе не заданы.'},
  {id:'campus',title:'ОбнинскТех — севернее Университетской улицы',section:'Разделы 3.2 и 3.4',streets:['Университетская'],description:'Создание ОбнинскТех на базе ИАТЭ НИЯУ МИФИ, развитие инженерной и транспортной инфраструктуры севернее улицы Университетской.',location:'Показана существующая улица. Контур кампуса и перечень строящихся корпусов не приведены.'},
  {id:'kurchatov',title:'Продолжение улицы Курчатова',section:'Раздел 3.4',streets:['Курчатова'],description:'Строительство продолжения улицы Курчатова — автодороги «Обнинск — Кабицино — Лапшинка» для транспортной доступности ОбнинскТех.',location:'Показана существующая улица. Трасса будущего продолжения в документе не приложена.'},
  {id:'industrial',title:'Производственные зоны у Киевского шоссе',section:'Раздел 3.4; приложение В',streets:['Киевское шоссе'],description:'Наполнение производственных зон вдоль Киевского шоссе, подведение сетей и размещение резидентов в новой зоне инновационного развития; завершение площадки-1 Технопарка.',location:'Шоссе служит ориентиром. Утверждённые границы отдельных площадок в тексте не приведены.'},
  {id:'center',title:'Городской центр: пересечение Маркса и Ленина',section:'Раздел 3.4',streets:['Маркса','Ленина'],description:'Формирование общественного городского центра на пересечении проспектов Маркса и Ленина и связного городского пространства.',location:'Выделены существующие проспекты как ориентиры. Это не границы будущего центра и не список изменяемых домов.'},
  {id:'protva',title:'Набережная реки Протвы',section:'Разделы 3.3 и 3.4',description:'Новая прогулочная зона и пешеходные связи за счёт благоустройства набережной Протвы.',location:'Показано существующее русло OSM. Проектный контур набережной и сроки участков не указаны.',extra:true},
  {id:'tourism',title:'Турлики, «Бодрая жизнь» и Музей истории',section:'Раздел 3.3, приоритет 5',objectIds:['b35153731'],description:'Визит-центр во флигеле усадьбы Турлики-Михайловское, пешеходные треки, реконструкция школы-колонии «Бодрая жизнь» и капитальный ремонт Музея истории Обнинска.',location:'Найдены существующие усадьба и музей в OSM. Будущая геометрия работ и индивидуальные сроки не заданы.',extra:true},
  {id:'transport',title:'Въезды, вокзал, автостанция и парковочные пространства',section:'Раздел 3.3, приоритет 4',description:'Реконструкция Северного и строительство Южного въездов, обновление вокзала и автостанции, оптимизация парковочных пространств.',location:'Точные участки строительства и их сроки не указаны; проектная геометрия не выдумывается.'},
  {id:'utilities',title:'Коллектор, очистные сооружения и водозабор',section:'Раздел 3.3, приоритет 4',description:'Завершение нового магистрального канализационного коллектора, модернизация очистных сооружений, новый подземный водозабор и обновление очистки питьевой воды.',location:'Адресный перечень и трассы коммуникаций в документе не приложены.'},
  {id:'ecology',title:'Парки, скверы, экоцентры и электрозаправки',section:'Раздел 3.3, приоритеты 1 и 6',description:'Реконструкция парков и скверов, расширение сети экоцентров, сеть электрозаправочных станций и развитие экологичного транспорта.',location:'Конкретные зоны и адреса объектов не перечислены; существующие парки не выдаются за утверждённые места новых работ.'}
];
export function phaseForYear(year){return phases.find(p=>year>=p.start&&year<=p.end);}
export function milestoneForYear(year){const phase=phaseForYear(year);return phase?{year:phase.end,...targets[phase.end]}:null;}
export function relatedBuildings(objects,directionId='all'){
  const chosen=directions.filter(d=>directionId==='all'||d.id===directionId);
  const streets=chosen.flatMap(d=>d.streets||[]),ids=new Set(chosen.flatMap(d=>d.objectIds||[]));
  return objects.filter(o=>['home','building','school','clinic','shop'].includes(o.kind)&&(ids.has(o.id)||streets.some(street=>o.name?.toLowerCase().includes(street.toLowerCase()))));
}
export function streetFeatures(context,directionId='all'){
  const located=directions.filter(d=>d.streets&&(directionId==='all'||d.id===directionId));
  const streets=context.features.flatMap(f=>{
    const matched=located.filter(d=>f.properties?.kind==='road'&&d.streets.some(street=>f.properties.name?.toLowerCase().includes(street.toLowerCase())));
    return matched.length?[{...f,properties:{...f.properties,planTitle:matched.map(d=>d.title).join('; ')}}]:[];
  });
  return [...streets,...extraGeometry.features.filter(f=>directionId==='all'||f.properties.direction===directionId)];
}
