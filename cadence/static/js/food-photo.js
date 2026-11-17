// Real pictures of foods (TheMealDB's ingredient pictures, served by cadence at api/recipe-ingredient/<name>).
// Any element with data-food="<food name>" gets the picture of that food when there is one that really is that food;
// when there is none, nothing changes (never a made-up or "close enough" picture). Also for what is added to the page later.
(function () {
  const KEY = 'cadence_food_photos2';
  const MAX_AGE = 3 * 24 * 3600 * 1000;
  let names = null; // lower-case name -> TheMealDB name
  // Words that only say how a food is cooked or cut: they do not change which picture it is.
  const MODIFIERS = new Set(['raw', 'cooked', 'boiled', 'grilled', 'fried', 'baked', 'roasted', 'steamed', 'fresh', 'whole', 'sliced',
    'chopped', 'diced', 'plain', 'large', 'small', 'medium', 'lean', 'skinless', 'boneless', 'organic', 'natural', 'white', 'brown',
    'red', 'green', 'yellow', 'sweet', 'ripe', 'frozen', 'canned', 'tinned', 'scrambled', 'mashed', 'hard', 'soft']);
  // Spanish names of common foods (the staples and what the photo says) -> the English ingredient that has a picture.
  const ES = [
    ['pechuga de pollo', 'chicken breast'], ['muslo de pollo', 'chicken thighs'], ['alitas de pollo', 'chicken wings'], ['carne molida', 'minced beef'],
    ['aceite de oliva', 'olive oil'], ['frijoles negros', 'black beans'], ['frijoles rojos', 'kidney beans'], ['leche de coco', 'coconut milk'],
    ['crema agria', 'sour cream'], ['queso crema', 'cream cheese'], ['mantequilla de mani', 'peanut butter'], ['papas fritas', 'fries'],
    ['arroz', 'rice'], ['pollo', 'chicken'], ['huevo', 'eggs'], ['huevos', 'eggs'], ['res', 'beef'], ['bistec', 'beef'], ['cerdo', 'pork'],
    ['tocino', 'bacon'], ['jamon', 'ham'], ['salchicha', 'sausages'], ['salmon', 'salmon'], ['atun', 'tuna'], ['camarones', 'prawns'],
    ['camaron', 'prawns'], ['tilapia', 'white fish'], ['pescado', 'white fish'], ['garbanzos', 'chickpeas'], ['lentejas', 'lentils'],
    ['papa', 'potatoes'], ['papas', 'potatoes'], ['pure de papas', 'potatoes'], ['platano', 'plantain'], ['banano', 'banana'], ['guineo', 'banana'],
    ['naranja', 'orange'], ['limon', 'lime'], ['aguacate', 'avocado'], ['tomate', 'tomatoes'], ['cebolla', 'onion'], ['ajo', 'garlic'],
    ['zanahoria', 'carrots'], ['brocoli', 'broccoli'], ['lechuga', 'lettuce'], ['ensalada', 'lettuce'], ['espinaca', 'spinach'],
    ['pepino', 'cucumber'], ['maiz', 'sweetcorn'], ['pan', 'bread'], ['tortilla', 'tortillas'], ['queso', 'cheese'], ['leche', 'milk'],
    ['yogur', 'yogurt'], ['mantequilla', 'butter'], ['azucar', 'sugar'], ['avena', 'oats'], ['fresas', 'strawberries'], ['pina', 'pineapple'],
    ['mango', 'mango'], ['uvas', 'grapes'], ['sandia', 'watermelon'], ['helado', 'ice cream'], ['miel', 'honey'], ['yuca', 'cassava'],
    // American names that the picture list spells the British way
    ['eggplant', 'aubergine'], ['zucchini', 'courgettes'], ['cilantro', 'coriander'], ['ground beef', 'minced beef'], ['shrimp', 'prawns'],
    ['scallion', 'spring onions'], ['green onion', 'spring onions'], ['cornstarch', 'corn flour'], ['heavy cream', 'double cream'],
    ['powdered sugar', 'icing sugar'], ['garbanzo', 'chickpeas'],
    ['pasta', 'spaghetti'], ['espagueti', 'spaghetti'], ['pimiento', 'red pepper'], ['champinones', 'mushrooms'], ['hongos', 'mushrooms'],
    // More Spanish names whose picture TheMealDB does have (17 nov 2026). Longer names first where one starts like another.
    ['platano maduro frito', 'fried ripe bananas'], ['maduro frito', 'fried ripe bananas'], ['maduros', 'fried ripe bananas'],
    ['papaya verde', 'green papaya'], ['name', 'white yam'], ['malanga', 'taro'], ['otoe', 'taro'], ['calabaza', 'pumpkin'],
    ['zapallo', 'pumpkin'], ['auyama', 'pumpkin'], ['frijoles pintos', 'pinto beans'], ['frijoles refritos', 'refried beans'],
    ['frijoles negros', 'black beans'], ['habichuelas', 'kidney beans'], ['vainitas', 'green beans'], ['ejotes', 'green beans'],
    ['arroz integral', 'brown rice'], ['tortilla de maiz', 'corn tortillas'], ['tortilla de harina', 'flour tortilla'], ['bacalao', 'salt cod'],
    ['sardinas', 'sardines'], ['chorizo', 'chorizo'], ['pavo', 'turkey'], ['mani', 'peanuts'], ['cacahuate', 'peanuts'], ['almendras', 'almonds'],
    ['maranon', 'cashews'], ['manzana', 'apples'], ['pera', 'pears'], ['durazno', 'peaches'], ['melocoton', 'peaches'], ['arandanos', 'blueberries'],
    ['frambuesas', 'raspberries'], ['maracuya', 'passion fruit pulp'], ['jugo de naranja', 'orange juice'], ['jugo de pina', 'pineapple juice'],
    ['pina', 'pineapple chunks'], ['coco', 'coconut'], ['tamarindo', 'tamarind pulp'], ['fruta de pan', 'breadfruit'], ['callaloo', 'callaloo'],
    ['ackee', 'ackee'], ['higado de pollo', 'chicken liver'], ['muslos de pollo', 'chicken thighs'], ['piernas de pollo', 'chicken legs'],
    ['chuleta de cerdo', 'pork chops'], ['costillas de cerdo', 'pork back ribs'], ['camote', 'sweet potatoes'], ['batata', 'sweet potatoes'],
    ['repollo', 'cabbage'], ['col', 'cabbage'], ['col rizada', 'kale'], ['pepinillo', 'cucumber'], ['calamar', 'squid'], ['pulpo', null],
    ['langosta', 'lobster'], ['mejillones', 'mussels'], ['almejas', 'clams'], ['salchichon', null], ['cerveza', 'beer'], ['vino tinto', 'red wine'],
    ['vino blanco', 'white wine'], ['leche condensada', 'sweetened condensed milk'], ['leche evaporada', 'evaporated milk'], ['leche de almendras', 'almond milk'],
    ['crema de leche', 'double cream'], ['galletas maria', 'maria cookies'], ['mayonesa', 'mayonnaise'], ['ketchup', 'tomato ketchup'],
    ['salsa de tomate', 'tomato ketchup'], ['mostaza', 'mustard'], ['salsa de soya', 'soy sauce'], ['tofu', 'tofu'], ['quinoa', 'quinoa'],
    ['cuscus', 'couscous'], ['fideos', 'noodles'], ['macarrones', 'macaroni'], ['lasana', 'lasagne sheets'], ['nutella', 'nutella'],
    ['mermelada', 'jam'], ['muffin', 'muffins'], ['cuajada', 'cheese curds'],
  ].sort((a, b) => b[0].length - a[0].length); // the longest Spanish name that fits wins ("frijoles negros" before "frijoles")
  // Pictures cadence ships itself (Wikimedia Commons, free licences, chosen one by one): foods TheMealDB has no picture for.
  let local = []; // [{names: [plain names], src}]
  const plain = (t) => String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z ]+/g, ' ').replace(/\s+/g, ' ').trim();

  function load() {
    try {
      const saved = JSON.parse(localStorage.getItem(KEY) || 'null');
      if (saved && saved.names && (saved.names.length || (saved.local || []).length) && Date.now() - saved.at < MAX_AGE) { use(saved.names, saved.local); return Promise.resolve(); }
    } catch { /* no storage */ }
    return fetch('api/food-photos', { cache: 'no-store' }).then((r) => (r.ok ? r.json() : null)).then((data) => {
      if (!data || (!(data.names || []).length && !(data.local || []).length)) return;
      try { localStorage.setItem(KEY, JSON.stringify({ at: Date.now(), names: data.names, local: data.local || [] })); } catch { /* full */ }
      use(data.names, data.local);
    }).catch(() => {});
  }
  function use(list, own) {
    names = new Map(list.map((n) => [n.toLowerCase(), n]));
    local = (own || []).map((item) => ({ names: (item.names || []).map(plain).filter(Boolean).sort((a, b) => b.length - a.length), src: item.src }))
      .filter((item) => item.names.length && /^static\/food-photos\/[a-z0-9_-]+\.jpg$/.test(item.src || ''));
    hydrate();
  }
  // A picture of our own: the whole name, or the name followed by more words ("arepa con queso" -> arepa).
  function ownPicture(text) {
    let best = null;
    for (const item of local) {
      for (const n of item.names) {
        if ((text === n || text.startsWith(`${n} `)) && (!best || n.length > best.len)) best = { len: n.length, src: item.src };
      }
    }
    return best && best.src;
  }

  function find(phrase) {
    if (!phrase) return null;
    for (const p of [phrase, `${phrase}s`, `${phrase}es`, phrase.replace(/es$/, ''), phrase.replace(/s$/, '')]) if (names.has(p)) return names.get(p);
    return null;
  }

  // The picture of a food, or null. "Grilled chicken breast, skinless" -> Chicken Breast; "Chicken soup" -> nothing.
  // Returns {own: src} for one of cadence's own pictures, or TheMealDB's ingredient name.
  function match(name) {
    if (!names) return null;
    const text = plain(String(name).split(/[,(]/)[0]);
    if (!text) return null;
    const own = ownPicture(text);
    if (own) return { own };
    const es = ES.find(([word]) => text === word || text.startsWith(`${word} `));
    if (es) return find(es[1]);
    // the whole name first, then without the descriptive words in front ("grilled", "white"...): the food is what is left
    let words = text.split(' ');
    while (words.length) {
      const hit = find(words.join(' '));
      if (hit) return hit;
      if (!MODIFIERS.has(words[0])) return null;
      words = words.slice(1);
    }
    return null;
  }
  const url = (name) => {
    const hit = match(name);
    if (!hit) return null;
    if (hit.own) return hit.own;
    return `api/recipe-ingredient/${encodeURIComponent(hit.toLowerCase().split(/\s+/).join('_'))}`;
  };

  function hydrate(root) {
    if (!names) return;
    (root || document).querySelectorAll('[data-food]:not([data-food-done])').forEach((el) => {
      el.setAttribute('data-food-done', '');
      const src = url(el.dataset.food);
      if (!src) return;
      el.classList.add('food-pic');
      el.style.backgroundImage = `url('${src}')`;
    });
  }

  window.cadenceFoodPhoto = { url, match, hydrate };
  const start = () => {
    load();
    new MutationObserver(() => hydrate()).observe(document.documentElement, { childList: true, subtree: true });
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
