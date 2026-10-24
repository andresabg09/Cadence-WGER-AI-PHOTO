"""Alimentos basicos YA PREPARADOS (como se comen), con valores estandar por 100 g.

El catalogo de wger sale de productos de supermercado "como se venden": "White rice" es arroz
CRUDO (340 kcal), pero en un plato es arroz cocido (130 kcal). Este script agrega ~90 basicos
preparados en ingles y espanol y los marca con source_name='cadence'; la busqueda de cadence
les da prioridad. Valores aproximados tipo USDA (kcal, proteina g, carbohidratos g, grasa g).

    python3 manage.py shell -c "exec(open('/tmp/seed_staples.py').read())"

Se puede ejecutar varias veces: cada alimento tiene un uuid fijo y se actualiza.
"""
import os
import uuid

SOURCE = "cadence"

# (english, espanol, kcal, protein, carbs, fat, fiber)
STAPLES = [
    # cereales y tuberculos
    ("Cooked white rice", "Arroz blanco cocido", 130, 2.7, 28.2, 0.3, 0.4),
    ("Cooked brown rice", "Arroz integral cocido", 123, 2.7, 25.6, 1.0, 1.6),
    ("Cooked pasta", "Pasta cocida", 158, 5.8, 30.9, 0.9, 1.8),
    ("Cooked quinoa", "Quinoa cocida", 120, 4.4, 21.3, 1.9, 2.8),
    ("Cooked oatmeal", "Avena cocida", 71, 2.5, 12.0, 1.5, 1.7),
    ("Boiled potato", "Papa cocida", 87, 1.9, 20.1, 0.1, 1.8),
    ("Mashed potatoes", "Pure de papas", 113, 2.0, 16.9, 4.2, 1.5),
    ("French fries", "Papas fritas", 312, 3.4, 41.4, 14.7, 3.8),
    ("Boiled yuca", "Yuca cocida", 160, 1.4, 38.1, 0.3, 1.8),
    ("Boiled corn", "Maiz cocido", 96, 3.4, 21.0, 1.5, 2.4),
    ("White bread", "Pan blanco", 265, 9.0, 49.0, 3.2, 2.7),
    ("Whole wheat bread", "Pan integral", 247, 13.0, 41.3, 3.4, 6.0),
    ("Corn tortilla", "Tortilla de maiz", 218, 5.7, 44.6, 2.9, 6.3),
    # legumbres
    ("Cooked black beans", "Frijoles negros cocidos", 132, 8.9, 23.7, 0.5, 8.7),
    ("Cooked red beans", "Frijoles rojos cocidos", 127, 8.7, 22.8, 0.5, 6.4),
    ("Cooked pinto beans", "Frijoles pintos cocidos", 143, 9.0, 26.2, 0.7, 9.0),
    ("Cooked chickpeas", "Garbanzos cocidos", 164, 8.9, 27.4, 2.6, 7.6),
    ("Cooked lentils", "Lentejas cocidas", 116, 9.0, 20.1, 0.4, 7.9),
    ("Cooked pigeon peas", "Guandu cocido", 121, 6.8, 23.3, 0.4, 5.1),
    # carnes, pescado, huevos
    ("Grilled chicken breast", "Pechuga de pollo a la plancha", 165, 31.0, 0.0, 3.6, 0.0),
    ("Roasted chicken thigh", "Muslo de pollo al horno", 209, 26.0, 0.0, 10.9, 0.0),
    ("Cooked ground beef", "Carne molida cocida", 250, 26.0, 0.0, 15.0, 0.0),
    ("Grilled beef steak", "Bistec de res a la plancha", 206, 30.0, 0.0, 8.5, 0.0),
    ("Cooked bacon", "Tocino cocido", 541, 37.0, 1.4, 42.0, 0.0),
    ("Baked salmon", "Salmon al horno", 206, 22.1, 0.0, 12.4, 0.0),
    ("Grilled tilapia", "Tilapia a la plancha", 128, 26.2, 0.0, 2.7, 0.0),
    ("Canned tuna in water", "Atun en agua", 116, 25.5, 0.0, 0.8, 0.0),
    ("Cooked shrimp", "Camarones cocidos", 99, 24.0, 0.2, 0.3, 0.0),
    ("Boiled egg", "Huevo cocido", 155, 12.6, 1.1, 10.6, 0.0),
    ("Scrambled eggs", "Huevos revueltos", 149, 10.0, 1.6, 11.0, 0.0),
    ("Fried egg", "Huevo frito", 196, 13.6, 0.8, 14.8, 0.0),
    # lacteos
    ("Whole milk", "Leche entera", 61, 3.2, 4.8, 3.3, 0.0),
    ("Plain yogurt", "Yogur natural", 61, 3.5, 4.7, 3.3, 0.0),
    ("Cheddar cheese", "Queso cheddar", 403, 24.9, 1.3, 33.1, 0.0),
    ("Mozzarella cheese", "Queso mozzarella", 280, 27.5, 3.1, 17.1, 0.0),
    # verduras
    ("Green salad", "Ensalada verde", 17, 1.2, 3.3, 0.2, 1.3),
    ("Tomato", "Tomate", 18, 0.9, 3.9, 0.2, 1.2),
    ("Cucumber", "Pepino", 15, 0.7, 3.6, 0.1, 0.5),
    ("Raw carrot", "Zanahoria cruda", 41, 0.9, 9.6, 0.2, 2.8),
    ("Boiled carrots", "Zanahoria cocida", 35, 0.8, 8.2, 0.2, 3.0),
    ("Boiled broccoli", "Brocoli cocido", 35, 2.4, 7.2, 0.4, 3.3),
    ("Avocado", "Aguacate", 160, 2.0, 8.5, 14.7, 6.7),
    ("Fried plantain", "Platano frito", 267, 1.5, 39.0, 12.5, 2.3),
    # frutas
    ("Banana", "Banano", 89, 1.1, 22.8, 0.3, 2.6),
    ("Apple", "Manzana", 52, 0.3, 13.8, 0.2, 2.4),
    ("Orange", "Naranja", 47, 0.9, 11.8, 0.1, 2.4),
    ("Watermelon", "Sandia", 30, 0.6, 7.6, 0.2, 0.4),
    ("Pineapple", "Pina", 50, 0.5, 13.1, 0.1, 1.4),
    ("Mango", "Mango", 60, 0.8, 15.0, 0.4, 1.6),
    ("Papaya", "Papaya", 43, 0.5, 10.8, 0.3, 1.7),
    ("Grapes", "Uvas", 69, 0.7, 18.1, 0.2, 0.9),
    ("Strawberries", "Fresas", 32, 0.7, 7.7, 0.3, 2.0),
    # postres, platos y bebidas
    ("Vanilla ice cream", "Helado de vainilla", 207, 3.5, 23.6, 11.0, 0.7),
    ("Chocolate ice cream", "Helado de chocolate", 216, 3.8, 28.2, 11.0, 1.2),
    ("Cheese pizza", "Pizza de queso", 266, 11.0, 33.3, 10.4, 2.3),
    ("Orange juice", "Jugo de naranja", 45, 0.7, 10.4, 0.2, 0.2),
    ("Cola soda", "Gaseosa de cola", 42, 0.0, 10.6, 0.0, 0.0),
    ("Black coffee", "Cafe negro", 1, 0.1, 0.0, 0.0, 0.0),
    # grasas y untables
    ("Butter", "Mantequilla", 717, 0.9, 0.1, 81.1, 0.0),
    ("Olive oil", "Aceite de oliva", 884, 0.0, 0.0, 100.0, 0.0),
    ("Mayonnaise", "Mayonesa", 680, 1.0, 0.6, 74.9, 0.0),
    ("Ketchup", "Salsa de tomate", 101, 1.0, 27.4, 0.1, 0.3),
    ("Peanut butter", "Mantequilla de mani", 588, 25.1, 20.0, 50.4, 6.0),
    ("Honey", "Miel", 304, 0.3, 82.4, 0.0, 0.2),
]


def staple_uuid(language_code: str, name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"cadence-staple:{language_code}:{name.lower()}")


def staple_records(language_ids: dict) -> list[dict]:
    """Rows in the same JSON shape as wger's own dump, so wger's parser builds them."""
    records = []
    for en, es, kcal, protein, carbs, fat, fiber in STAPLES:
        for code, name in (("en", en), ("es", es)):
            if code not in language_ids:
                continue
            records.append({
                "uuid": str(staple_uuid(code, name)), "name": name, "common_name": name, "code": None, "brand": "",
                "language": language_ids[code], "energy": kcal, "protein": protein, "carbohydrates": carbs,
                "fat": fat, "fiber": fiber, "source_name": SOURCE, "source_url": "",
                "license_title": "cadence staples (approximate USDA values)",
            })
    return records


def main():
    from wger.core.models import Language
    from wger.nutrition.extract_info.wger import extract_info_from_wger_api
    from wger.nutrition.models import Ingredient

    language_ids = {lang.short_name: lang.id for lang in Language.objects.filter(short_name__in=["en", "es"])}
    created = updated = 0
    for record in staple_records(language_ids):
        fields = extract_info_from_wger_api(record).dict()
        fields.pop("uuid", None)
        _, was_created = Ingredient.objects.update_or_create(uuid=record["uuid"], defaults=fields)
        created += was_created
        updated += not was_created
    print(f"LISTO: {created} creados, {updated} actualizados ({len(STAPLES)} basicos x {len(language_ids)} idiomas).")
    for term in ("Cooked white rice", "Vanilla ice cream", "Arroz blanco cocido"):
        print(f"  '{term}':", Ingredient.objects.filter(name__iexact=term).count())


if not os.environ.get("CADENCE_NO_RUN"):
    main()
