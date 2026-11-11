// Real pictures of foods (TheMealDB's ingredient pictures, served by cadence at api/recipe-ingredient/<name>).
// Any element with data-food="<food name>" gets the picture of that food when there is one that really is that food;
// when there is none, nothing changes (never a made-up or "close enough" picture). Also for what is added to the page later.
(function () {
  const KEY = 'cadence_food_photos';
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
  ];
  const plain = (t) => String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z ]+/g, ' ').replace(/\s+/g, ' ').trim();

  function load() {
    try {
      const saved = JSON.parse(localStorage.getItem(KEY) || 'null');
      if (saved && saved.names && saved.names.length && Date.now() - saved.at < MAX_AGE) { use(saved.names); return Promise.resolve(); }
    } catch { /* no storage */ }
    return fetch('api/food-photos', { cache: 'no-store' }).then((r) => (r.ok ? r.json() : null)).then((data) => {
      if (!data || !data.names || !data.names.length) return;
      try { localStorage.setItem(KEY, JSON.stringify({ at: Date.now(), names: data.names })); } catch { /* full */ }
      use(data.names);
    }).catch(() => {});
  }
  function use(list) { names = new Map(list.map((n) => [n.toLowerCase(), n])); hydrate(); }

  function find(phrase) {
    if (!phrase) return null;
    for (const p of [phrase, `${phrase}s`, `${phrase}es`, phrase.replace(/es$/, ''), phrase.replace(/s$/, '')]) if (names.has(p)) return names.get(p);
    return null;
  }

  // The picture of a food, or null. "Grilled chicken breast, skinless" -> Chicken Breast; "Chicken soup" -> nothing.
  function match(name) {
    if (!names) return null;
    const text = plain(String(name).split(/[,(]/)[0]);
    if (!text) return null;
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
  const url = (name) => { const hit = match(name); return hit ? `api/recipe-ingredient/${encodeURIComponent(hit.toLowerCase().split(/\s+/).join('_'))}` : null; };

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
