"""
CDE2 custom models for CO2 hydrogenation catalysis text mining.

These models define grammar-based extractors that CDE2 uses to pull
structured records from scientific text without an LLM.

Each model produces records like:
  {
    "Compound": {"names": ["Cu-ZnO-Al2O3"]},
    "CO2Conversion": {"value": "45.2", "units": "%"},
    ...
  }

Three models are defined here:
  1. CO2Conversion   — CO2 conversion values
  2. ProductSelectivity — selectivity to a specific product
  3. ReactionConditions  — temperature and pressure

Usage (within enrich_chunks_cde.py or standalone):
  from models.catalysis import CO2Conversion, ProductSelectivity, ReactionConditions
  from chemdataextractor import Document
  from chemdataextractor.doc import Paragraph

  doc = Document(Paragraph("Cu/ZnO showed 42% CO2 conversion at 260 °C."),
                 models=[CO2Conversion, ReactionConditions])
  for r in doc.records:
      print(r.serialize())

Requirements:
  chemdataextractor2 installed and `cde data download` completed.
"""
from __future__ import annotations

# Guard import so this file can be imported even without CDE2 installed
# (enrich_chunks_cde.py checks availability before using models).
try:
    from chemdataextractor.model import (
        BaseModel,
        StringType,
        ModelType,
        ListType,
    )
    from chemdataextractor.model.units.quantity_model import QuantityModel, DimensionlessModel
    from chemdataextractor.model.units.temperature import TemperatureModel
    from chemdataextractor.model.units.pressure import PressureModel
    from chemdataextractor.parse.elements import (
        R, I, W, T, Optional, Any, OneOrMore, ZeroOrMore, Not,
        SkipTo, Group,
    )
    from chemdataextractor.parse.actions import join, merge
    from chemdataextractor.parse.auto import AutoSentenceParser, AutoTableParser
    from chemdataextractor.parse.quantity import QuantityParser

    _CDE2_AVAILABLE = True
except ImportError:
    _CDE2_AVAILABLE = False

# ---------------------------------------------------------------------------
# Helpers: shared grammar fragments
# ---------------------------------------------------------------------------
if _CDE2_AVAILABLE:
    # Connective words between compound and property
    _CONN = (
        I("showed") | I("exhibited") | I("achieved") | I("reached")
        | I("obtained") | I("reported") | I("with") | I("giving")
        | I("afforded") | I("demonstrated") | I("had")
    )

    # Words that introduce a compound (catalyst) name
    _OVER = I("over") | I("on") | I("with") | I("for") | I("using") | I("of")

    # ---------------------------------------------------------------------------
    # Model 1: CO2 Conversion
    # ---------------------------------------------------------------------------

    class CO2ConversionModel(DimensionlessModel):
        """
        Extracts CO2 conversion values from text.

        Matches patterns like:
          - "CO2 conversion of 45%"
          - "45% CO2 conversion"
          - "showed 45% conversion of CO2"
        """
        specifier = StringType(
            parse_expression=(
                (I("CO2") | I("CO₂")) + (I("conversion") | I("conv."))
                | I("conversion") + I("of") + (I("CO2") | I("CO₂"))
            ),
            required=True,
            contextual=True,
        )
        compound = ModelType(
            # Reuse CDE2 Compound to capture the catalyst name in context
            # Import lazily to avoid circular issues
            model_name="Compound",
            required=False,
            contextual=True,
        )
        parsers = [AutoSentenceParser(), AutoTableParser()]

    # ---------------------------------------------------------------------------
    # Model 2: Product Selectivity
    # ---------------------------------------------------------------------------

    class ProductSelectivityModel(DimensionlessModel):
        """
        Extracts product selectivity values.

        Matches patterns like:
          - "selectivity to ethanol of 32%"
          - "32% selectivity toward C2+ alcohols"
          - "ethanol selectivity: 32%"
        """
        specifier = StringType(
            parse_expression=(
                I("selectivity") + Optional(I("to") | I("toward") | I("for"))
                | I("sel.") + Optional(I("to") | I("toward"))
            ),
            required=True,
            contextual=True,
        )
        product = StringType(
            parse_expression=(
                I("ethanol") | I("methanol") | I("propanol") | I("butanol")
                | (I("C2") + Optional(W("+") | W("+")))
                | I("alcohols") | I("hydrocarbons") | I("CO") | I("CH4")
                | I("oxygenates") | I("higher") + I("alcohols")
            ),
            required=False,
            contextual=True,
        )
        compound = ModelType(model_name="Compound", required=False, contextual=True)
        parsers = [AutoSentenceParser(), AutoTableParser()]

    # ---------------------------------------------------------------------------
    # Model 3: Reaction Conditions (Temperature)
    # ---------------------------------------------------------------------------

    class ReactionTemperatureModel(TemperatureModel):
        """
        Extracts reaction temperatures.

        Matches patterns like:
          - "at 260 °C"
          - "reaction temperature of 300 °C"
          - "260–300 °C"
        """
        specifier = StringType(
            parse_expression=(
                I("temperature") | I("temp.") | I("at")
                | I("reaction") + I("temperature")
            ),
            required=False,
            contextual=True,
        )
        compound = ModelType(model_name="Compound", required=False, contextual=True)
        parsers = [AutoSentenceParser(), AutoTableParser()]

    # ---------------------------------------------------------------------------
    # Model 4: Reaction Conditions (Pressure)
    # ---------------------------------------------------------------------------

    class ReactionPressureModel(PressureModel):
        """
        Extracts reaction pressures.

        Matches patterns like:
          - "at 3 MPa"
          - "pressure of 30 bar"
          - "under 3–5 MPa"
        """
        specifier = StringType(
            parse_expression=(
                I("pressure") | I("P") | I("at") | I("under")
                | I("reaction") + I("pressure")
            ),
            required=False,
            contextual=True,
        )
        compound = ModelType(model_name="Compound", required=False, contextual=True)
        parsers = [AutoSentenceParser(), AutoTableParser()]

    # Expose the four models for import
    CO2Conversion = CO2ConversionModel
    ProductSelectivity = ProductSelectivityModel
    ReactionTemperature = ReactionTemperatureModel
    ReactionPressure = ReactionPressureModel

    ALL_MODELS = [
        CO2Conversion,
        ProductSelectivity,
        ReactionTemperature,
        ReactionPressure,
    ]

else:
    # Stub objects when CDE2 is not installed — allow safe import
    class _Stub:
        def __init__(self, name):
            self.__name__ = name
        def __repr__(self):
            return f"<CDE2 unavailable: {self.__name__}>"

    CO2Conversion = _Stub("CO2Conversion")
    ProductSelectivity = _Stub("ProductSelectivity")
    ReactionTemperature = _Stub("ReactionTemperature")
    ReactionPressure = _Stub("ReactionPressure")
    ALL_MODELS = []
