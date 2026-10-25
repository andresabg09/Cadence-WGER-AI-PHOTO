"""Units and the one question they hide: is this food measured in grams or in millilitres?

Everything is stored in the metric system (kg, cm, ml, g). The person only chooses how it is SHOWN. Solids are always
grams; liquids (soups, drinks) follow the person's liquid unit (ml or fl oz). For a liquid, 1 ml is counted as 1 g,
which is close enough for soups, juices and drinks (the catalog gives calories per 100 g).
"""

import re
import unicodedata

ML_PER_FLOZ = 29.5735
GLASS_ML = {"ml": 250, "oz": 237}  # one glass of water: 250 ml, or 8 fl oz (about 237 ml)
KG_PER_LB = 0.45359237
CM_PER_IN = 2.54

WEIGHT_UNITS = ("kg", "lb")
HEIGHT_UNITS = ("cm", "ft")
LIQUID_UNITS = ("ml", "oz")

# Words that make a food a liquid (accent-free, lower case, matched as whole words). Soups first: in Panama a "sancocho"
# or a "mondongo" is eaten with a spoon but measured as a liquid.
_LIQUID = re.compile(
    r"\b(sopa|sopas|caldo|caldos|consome|sancocho|mondongo|jugo|jugos|zumo|juice|leche|milk|batido|batidos|licuado|licuados|"
    r"shake|smoothie|refresco|refrescos|gaseosa|soda|coca|pepsi|sprite|fanta|bebida|bebidas|drink|cafe|coffee|te|tea|infusion|chicha|"
    r"horchata|cerveza|beer|vino|wine|agua|water|soup|broth|stew|chocolate caliente|hot chocolate)\b"
)
# ...unless it is something thick or dry that only shares the word.
_NOT_LIQUID = re.compile(
    r"\b(condensada|condensed|polvo|powder|dulce de leche|queso|cheese|helado|ice cream|galleta|cookie|barra|bar|"
    r"aguacate|chocolate bar|mantequilla|butter|yogur|yogurt|yoghurt|cereal)\b"
)


def _plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", (text or "").lower()) if not unicodedata.combining(c))


def is_liquid(name: str, flagged: bool | None = None) -> bool:
    """A food measured in millilitres: flagged by the person or the model, else guessed from its name."""
    if flagged is not None:
        return bool(flagged)
    plain = _plain(name)
    return bool(_LIQUID.search(plain)) and not _NOT_LIQUID.search(plain)
