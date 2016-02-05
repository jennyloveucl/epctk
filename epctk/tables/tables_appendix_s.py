"""
Tables for RdSAP
~~~~~~~~~~~~~~~~


"""
import os.path
from enum import Enum, IntEnum
import csv

from ..utils import SAPInputError
from ..elements import GlazingTypes, DwellingType
from ..elements.geographic import Country

_DATA_FOLDER = os.path.join(os.path.dirname(__file__), '..', 'data')


class AgeBand(IntEnum):
    A = 1
    B = 2
    C = 3
    D = 4
    E = 5
    F = 6
    G = 7
    H = 8
    I = 9
    J = 10
    K = 11

    @classmethod
    def from_letter(cls, letter):
        return cls.__members__[letter]

    @property
    def letter(self):
        return self.name


class WallMaterial(Enum):
    STONE_HARD = 'stone_hard'
    STONE_SANDSTONE = 'stone_sandstone'
    SOLID_BRICK = 'solid_brick'
    COB = 'cob'
    CAVITY = 'cavity'
    TIMBER = 'timber'
    SYSTEM = 'system'


class WallInsulation(Enum):
    INTERNAL = 'internal'
    EXTERNAL = 'external'
    FILL = 'fill'
    NONE = 'none'


# Age band 	England & Wales 	Scotland 	Northern Ireland
# A 	before 1900 	before 1919 	before 1919
# B 	1900-1929 	1919-1929 	1919-1929
# C 	1930-1949 	1930-1949 	1930-1949
# D 	1950-1966 	1950-1964 	1950-1973
# E 	1967-1975 	1965-1975 	1974-1977
# F 	1976-1982 	1976-1983 	1978-1985
# G 	1983-1990 	1984-1991 	1986-1991
# H 	1991-1995 	1992-1998 	1992-1999
# I 	1996-2002 	1999-2002 	2000-2006
# J 	2003-2006 	2003-2007 	(not applicable)
# K 	2007 onwards 	2008 onwards 	2007 onwards

# map ageband to year of construction:
TABLE_S1 = {
    Country.Scotland: {AgeBand.A: (None, 1919),
                       AgeBand.B: (1919, 1929),
                       AgeBand.C: (1930, 1949),
                       AgeBand.D: (1950, 1964),
                       AgeBand.E: (1965, 1975),
                       AgeBand.F: (1976, 1983),
                       AgeBand.G: (1984, 1991),
                       AgeBand.H: (1992, 1998),
                       AgeBand.I: (1999, 2002),
                       AgeBand.J: (2003, 2007),
                       AgeBand.K: (2008, None)},
    Country.NorthernIreland: {AgeBand.A: (None, 1919),
                              AgeBand.B: (1919, 1929),
                              AgeBand.C: (1930, 1949),
                              AgeBand.D: (1950, 1973),
                              AgeBand.E: (1974, 1977),
                              AgeBand.F: (1978, 1985),
                              AgeBand.G: (1986, 1991),
                              AgeBand.H: (1992, 1999),
                              AgeBand.I: (2000, 2006),
                              AgeBand.J: None,
                              AgeBand.K: (2007, None)},
    Country.England: {AgeBand.A: (0, 1900),
                      AgeBand.B: (1900, 1929),
                      AgeBand.C: (1930, 1949),
                      AgeBand.D: (1950, 1966),
                      AgeBand.E: (1967, 1975),
                      AgeBand.F: (1976, 1982),
                      AgeBand.G: (1983, 1990),
                      AgeBand.H: (1991, 1995),
                      AgeBand.I: (1996, 2002),
                      AgeBand.J: (2003, 2006),
                      AgeBand.K: (2007, None)}
}


def table_s1_age_band(building_age, country):
    country_table = TABLE_S1[country]

    for band, yr_range in country_table.items():
        if yr_range is None:
            continue
        start, end = yr_range
        start = start if start is not None else -9999
        end = end if end is not None else 9999

        if start < building_age <= end:
            return band


LIVING_AREA_FRACTION = [
    0.75, 0.5, 0.3, 0.25, 0.21, 0.18, 0.16, 0.14, 0.13, 0.12, 0.11, 0.1, 0.1, 0.09, 0.09
]


def living_area_fraction(n_rooms):
    return LIVING_AREA_FRACTION[int(n_rooms) - 1]


def u_roof(loft_ins_thickness_mm):
    return 1 / (1 / 2.3 + 0.021 * loft_ins_thickness_mm)


def lookup_wall_u_values(country, age_band, wall_material, wall_insulation):
    """
    Lookup U-values using table s6, s7, or s8 depending on the country

    Args:
        country:
        age_band:
        wall_material:
        wall_insulation:
    """
    table_nums = {
        Country.England: 6,
        Country.Wales: 6,
        Country.Scotland: 7,
        Country.NorthernIreland: 8
    }

    table_n = table_nums[country]

    table_lookup = {
        'Stone: granite or whin (as built)': (WallMaterial.STONE_HARD, WallInsulation.NONE),
        'Stone: sandstone (as built)': (WallMaterial.STONE_SANDSTONE, WallInsulation.NONE),
        'Solid brick (as built)': (WallMaterial.SOLID_BRICK, WallInsulation.NONE),
        'Stone/solid brick (external insulation)': (WallMaterial.SOLID_BRICK, WallInsulation.EXTERNAL),
        'Stone/solid brick (internal insulation)': (WallMaterial.SOLID_BRICK, WallInsulation.INTERNAL),
        'Cob (as built)': (WallMaterial.COB, WallInsulation.NONE),
        'Cob (external insulation)': (WallMaterial.COB, WallInsulation.EXTERNAL),
        'Cob (internal insulation)': (WallMaterial.COB, WallInsulation.INTERNAL),
        'Cavity (as built)': (WallMaterial.CAVITY, WallInsulation.NONE),
        'Filled cavity': (WallMaterial.CAVITY, WallInsulation.FILL),
        'Timber frame (as built)': (WallMaterial.TIMBER, WallInsulation.NONE),
        'Timber frame (internal insulation)': (WallMaterial.TIMBER, WallInsulation.INTERNAL),
        'System build (as built)': (WallMaterial.SYSTEM, WallInsulation.NONE),
        'System build (external insulation)': (WallMaterial.SYSTEM, WallInsulation.EXTERNAL),
        'System build (internal insulation)': (WallMaterial.SYSTEM, WallInsulation.INTERNAL),
    }

    table = {}
    with open(os.path.join(_DATA_FOLDER, "table_s{}.csv".format(table_n))) as csvfile:
        rdr = csv.DictReader(csvfile)
        for i, row in enumerate(rdr):
            wall_type = row.pop('WallType').strip()
            wall_type = table_lookup[wall_type]
            band_indexed = {AgeBand.from_letter(c): float(v) for c, v in row.items()}
            table[wall_type] = band_indexed

    try:
        return table[(wall_material, wall_insulation)][age_band]
    except KeyError:
        raise SAPInputError("No table s6/7/8 data for {}, {}, {}".format(age_band, wall_material, wall_insulation))


def lookup_wall_thickness(age_band, wall_material, wall_insulation):
    """
    Lookup wall thickness according to table s3

    Args:
        age_band (AgeBand):
        wall_material (WallMaterial):
        wall_insulation (WallInsulation):

    Returns:
        float wall thickness
    """
    # NOTE: make sure all these are tuples, don't remove commas by accident
    walltype_lookup = {
        'Stone as built': ((WallMaterial.STONE_HARD, WallMaterial.STONE_SANDSTONE), (WallInsulation.NONE,)),
        'Stone with internal or external insulation': ((WallMaterial.STONE_HARD, WallMaterial.STONE_SANDSTONE),
                                                       (WallInsulation.INTERNAL, WallInsulation.EXTERNAL)),
        'Solid brick as built': ((WallMaterial.SOLID_BRICK, ),
                                 (WallInsulation.NONE,)),
        'Solid brick with internal or external insulation': ((WallMaterial.SOLID_BRICK,),
                                                             (WallInsulation.INTERNAL, WallInsulation.EXTERNAL)),
        'Cavity': ((WallMaterial.CAVITY,),
                   (WallInsulation.NONE, WallInsulation.FILL)),
        'Timber frame (as built)': ((WallMaterial.TIMBER,),
                                    (WallInsulation.NONE,)),
        'Timber frame with internal insulation': ((WallMaterial.TIMBER,),
                                                  (WallInsulation.INTERNAL, )),
        'Cob': ((WallMaterial.COB,),
                (WallInsulation.NONE,)),
        'Cob with internal or external insulation': ((WallMaterial.COB,),
                                                     (WallInsulation.INTERNAL, WallInsulation.EXTERNAL)),
        'System build': ((WallMaterial.SYSTEM, ),
                         (WallInsulation.NONE,)),
        'System build with internal or external insulation': ((WallMaterial.SYSTEM,),
                                                              (WallInsulation.INTERNAL, WallInsulation.EXTERNAL)),

    }

    table = {}
    with open(os.path.join(_DATA_FOLDER, "table_s3.csv")) as csvfile:
        rdr = csv.DictReader(csvfile)
        for i, row in enumerate(rdr):
            wall_type = row.pop('WallType').strip()

            band_indexed = {AgeBand.from_letter(c): float(v) for c, v in row.items()}
            table[wall_type] = band_indexed

    for wall_type, row in table.items():
        wall_defs = walltype_lookup[wall_type]
        if wall_material in wall_defs[0] and wall_insulation in wall_defs[1]:
            return row[age_band]
    else:
        raise SAPInputError("No table s3 data for {}, {}, {}".format(age_band, wall_material, wall_insulation))

#
# CAVITY_WALL_U_VALUES = {  # Masonry cavity as built
#     AgeBand.A: 2.1,
#     AgeBand.B: 1.6,
#     AgeBand.C: 1.6,
#     AgeBand.D: 1.6,
#     AgeBand.E: 1.6,
#     AgeBand.F: 1.0,
#     AgeBand.G: 0.6,
#     AgeBand.H: 0.6,
# }
#
# FILLED_CAVITY_WALL_U_VALUES = {  # Masonry cavity filled
#     AgeBand.A: 0.5,
#     AgeBand.B: 0.5,
#     AgeBand.C: 0.5,
#     AgeBand.D: 0.5,
#     AgeBand.E: 0.5,
#     AgeBand.F: 0.4,
#     AgeBand.G: 0.35,
#     AgeBand.H: 0.35,
# }
#
# SOLID_BRICK_U_VALUES = {  # Solid brick as built
#     AgeBand.A: 2.1,
#     AgeBand.B: 2.1,
#     AgeBand.C: 2.1,
#     AgeBand.D: 2.1,
#     AgeBand.E: 1.7,
#     AgeBand.F: 1.0,
#     AgeBand.G: .6,
#     AgeBand.H: .6,
# }
#
# """
# SOLID_BRICK_U_VALUES= { ### Solid brick as built
#     AgeBands.A:1.7,
#     AgeBands.B:1.7,
#     AgeBands.C:1.7,
#     AgeBands.D:1.7,
#     AgeBands.E:1.7,
#     AgeBands.F:1.0,
#     AgeBands.G:.6,
#     AgeBands.H:.6,
# }"""
# TIMBER_WALL_U_VALUES = {  # Timber frame
#     AgeBand.A: 2.5,
#     AgeBand.B: 1.9,
#     AgeBand.C: 1.9,
#     AgeBand.D: 1.0,
#     AgeBand.E: 0.8,
#     AgeBand.F: 0.45,
#     AgeBand.G: 0.4,
#     AgeBand.H: 0.4,
# }
#
# CONCRETE_WALL_U_VALUES = {  # System build as built
#     AgeBand.A: 2.0,
#     AgeBand.B: 2.0,
#     AgeBand.C: 2.0,
#     AgeBand.D: 2.0,
#     AgeBand.E: 1.7,
#     AgeBand.F: 1.0,
#     AgeBand.G: 0.6,
#     AgeBand.H: 0.6,
# }
#
# CAVITY_WALL_THICKNESS = {
#     AgeBand.A: .25,
#     AgeBand.B: .25,
#     AgeBand.C: .25,
#     AgeBand.D: .25,
#     AgeBand.E: .25,
#     AgeBand.F: .26,
#     AgeBand.G: .27,
#     AgeBand.H: .27,
# }
#
# SOLID_WALL_THICKNESS = {
#     AgeBand.A: .22,
#     AgeBand.B: .22,
#     AgeBand.C: .22,
#     AgeBand.D: .22,
#     AgeBand.E: .24,
#     AgeBand.F: .25,
#     AgeBand.G: .27,
#     AgeBand.H: .27,
# }
#
# TIMBER_WALL_THICKNESS = {
#     AgeBand.A: .15,
#     AgeBand.B: .15,
#     AgeBand.C: .15,
#     AgeBand.D: .25,
#     AgeBand.E: .27,
#     AgeBand.F: .27,
#     AgeBand.G: .27,
#     AgeBand.H: .27,
# }
#
# CONCRETE_WALL_THICKNESS = {
#     AgeBand.A: .25,
#     AgeBand.B: .25,
#     AgeBand.C: .25,
#     AgeBand.D: .25,
#     AgeBand.E: .25,
#     AgeBand.F: .30,
#     AgeBand.G: .30,
#     AgeBand.H: .30,
# }
#

# Table S5 (contains miscellaneous substitutions)


def n_fans_and_vents(age_band, n_rooms):
    if age_band <= AgeBand.E:
        return 0
    elif age_band <= AgeBand.G:
        return 1
    else:
        if n_rooms <= 2:
            return 1
        elif n_rooms <= 5:
            return 2
        elif n_rooms <= 8:
            return 3
        else:
            return 4


def floor_infiltration(age_band):
    return 0.2 if age_band <= AgeBand.E else 0.1


def has_draught_lobby(dwelling_type):
    """
    House or bungalow: no
    Flat or maisonette: yes if heated or unheated corridor

    Args:
        dwelling_type:

    Returns:

    """
    return dwelling_type == DwellingType.FLAT


def percent_draught_stripping(openings):
    """
    *Table S5*

    Windows draughtstripped equal to percentage of triple, double or secondary glazing
    (glazing in a non-separated conservatory is included in the calculation of the percentage).

    Doors not draughtstripped

    Args:
        dwelling:

    Returns:
        float percentage draft stripped
    """
    count_openings = 0
    count_non_single = 0
    for opening in openings:
        count_openings += 1
        if opening.get('glazing_type') in [GlazingTypes.DOUBLE, GlazingTypes.TRIPLE, GlazingTypes.SECONDARY]:
            count_non_single += 1

    return 100 * count_non_single / count_openings


def num_sheltered_sides(dwelling_type, n_floors):
    """
    4 for flat/maisonette up to third storey above ground level 2 in other cases
    Args:
        dwelling_type:
        n_floors:

    Returns:
        int number of sheltered sides
    """

    if dwelling_type in [DwellingType.FLAT, DwellingType.MAISONETTE] and n_floors < 3:
        return 4
    else:
        return 2


### END table s5 ###


def primary_pipework_insulated():
    return False


def has_hw_time_control(age_band):
    if age_band <= AgeBand.I:
        return False
    else:
        return True


class Glazing:
    def __init__(self, light_transmittance, gvalue, Uvalue, draught_proof):
        self.properties = {
            'light_transmittance': light_transmittance,
            'gvalue': gvalue,
            'Uglazing': Uvalue,
            'glazing_is_draught_proof': draught_proof
        }

    def apply_to(self, target):
        # target.glazing=self.properties
        for k, v in list(self.properties.items()):
            setattr(target, k, v)


GLAZING_TYPES = {
    GlazingTypes.SINGLE: Glazing(0.9, 0.85, 1 / (0.04 + 1 / 4.8), False),
    ### Should vary with age
    GlazingTypes.DOUBLE: Glazing(0.8, 0.76, 1 / (0.04 + 1 / 3.1), True)

    # also need secondary and triple glazing
}
