"""
Improvement measures
~~~~~~~~~~~~~~~~~~~~


"""

from ..elements import HeatLossElementTypes, HeatLossElement, OpeningType, GlazingTypes, Opening, OvershadingTypes, \
    VentilationTypes, HeatEmitters, CylinderInsulationTypes, HeatingTypes, PVOvershading
from ..fuels import fuel_from_code
from .. import worksheet
from ..configure import lookup_sap_tables
from ..dwelling import DwellingResults
from ..tables import table_2a_hot_water_vol_factor


def apply_low_energy_lighting(base, dwelling):
    """
    Apply low energy lighting improvement
    :param base: base performance is ignored, but necessary to maintain consisten interface
    :param dwelling:
    :return:
    """
    if ((dwelling.get('low_energy_bulb_ratio') and dwelling.low_energy_bulb_ratio == 1) or
                dwelling.lighting_outlets_low_energy == dwelling.lighting_outlets_total):
        return False

    dwelling.low_energy_bulb_ratio = 1
    return True


def needs_separate_solar_cylinder(base):
    """

    Args:
        base: The base dwelling configuration
    Returns:

    """
    if base.water_sys.system_type in [HeatingTypes.cpsu,
                                      HeatingTypes.combi,
                                      HeatingTypes.storage_combi,
                                      HeatingTypes.heat_pump,
                                      HeatingTypes.pcdf_heat_pump]:
        return True

    if base.get('instantaneous_pou_water_heating'):
        return True

    if base.water_sys.system_type == HeatingTypes.community and base.get('hw_cylinder_volume') is None:
        return True

    if (base.water_sys.system_type == HeatingTypes.microchp
        and base.water_sys.has_integral_store):
        return True

    return False


def apply_solar_hot_water(base, dwelling):
    """
    Apply the solar hot water improvement
    Args:
        base: The base dwelling configuration
        dwelling: The improved dwelling configuration

    Returns:

    """
    if dwelling.is_flat:
        return False

    if dwelling.get('solar_collector_aperture', 0) > 0:
        return False

    dwelling.solar_collector_aperture = 3
    dwelling.collector_zero_loss_effy = .7
    dwelling.collector_heat_loss_coeff = 1.8
    dwelling.collector_orientation = 180.
    dwelling.collector_pitch = 30.
    dwelling.collector_overshading = PVOvershading.MODEST
    dwelling.has_electric_shw_pump = True
    dwelling.solar_dedicated_storage_volume = 75.

    if needs_separate_solar_cylinder(base):
        dwelling.solar_storage_combined_cylinder = False
    else:
        assert dwelling.hw_cylinder_volume > 0
        dwelling.solar_storage_combined_cylinder = True

        if dwelling.hw_cylinder_volume < 190 and dwelling.get('measured_cylinder_loss'):
            old_vol_fac = table_2a_hot_water_vol_factor(dwelling.hw_cylinder_volume)
            new_vol_fac = table_2a_hot_water_vol_factor(190)
            dwelling.measured_cylinder_loss *= new_vol_fac * 190 / (old_vol_fac * dwelling.hw_cylinder_volume)
            dwelling.hw_cylinder_volume = 190
        else:
            dwelling.hw_cylinder_volume = max(dwelling.hw_cylinder_volume, 190.)

    return True


def apply_pv(base, dwelling):
    """
    Apply PV improvements. Only valid if the dwelling is not a flat
    and there are no photovoltaic systems already installed

    Args:
        base: The base dwelling configuration
        dwelling: The improved dwelling configuration

    Returns:
        Update the dwelling configuration and return bool indicating
        whether the PV improvement applies
    """
    # TODO: check whether the is_flat etc checks should be on the base dwelling or the improved one
    if dwelling.is_flat:
        return False

    if len(dwelling.get('photovoltaic_systems', [])) > 0:
        return False

    pv_system = dict(
            kWp=2.5,
            pitch=30,
            orientation=180,
            overshading_category=PVOvershading.MODEST
    )
    dwelling.photovoltaic_systems = [pv_system, ]
    return True


def apply_wind(base, dwelling):
    """

    Args:
        base: The base dwelling configuration
        dwelling: The improved dwelling configuration

    Returns:
        Update the dwelling configuration and return bool indicating
        whether the wind improvement applies
    """
    if dwelling.is_flat:
        return False

    if dwelling.get('N_wind_turbines', 0) > 0:
        return False

    dwelling.N_wind_turbines = 1
    dwelling.wind_turbine_rotor_diameter = 2.0
    dwelling.wind_turbine_hub_height = 2.0
    return True


IMPROVEMENTS = [
    ("E", 0.45, apply_low_energy_lighting),
    ("N", 0.95, apply_solar_hot_water),
    ("U", 0.95, apply_pv),
    ("V", 0.95, apply_wind),
]


def apply_previous_improvements(base, target, previous):
    for improvement in previous:
        name, min_val, improve = [improve for improve in IMPROVEMENTS if improve[0] == improvement.tag][0]
        improve(base, target)
        improve(base, target)


def run_improvements(dwelling):
    """
    Need to run the dwelling twice: once with pcdf fuel prices to
    get cost change, once with normal SAP fuel prices to get change
    in SAP rating

    :param dwelling:
    :return:
    """

    base_dwelling_pcdf_prices = DwellingResults(dwelling)
    # print('478: ', dwelling.get('hw_cylinder_volume'))
    # print('479: ', base_dwelling_pcdf_prices.get('hw_cylinder_volume'))

    base_dwelling_pcdf_prices.reduced_gains = False
    base_dwelling_pcdf_prices.use_pcdf_fuel_prices = True
    lookup_sap_tables(base_dwelling_pcdf_prices)

    worksheet.perform_full_calc(base_dwelling_pcdf_prices)
    worksheet.sap(base_dwelling_pcdf_prices)

    dwelling.improvement_results = ImprovementResults()

    base_cost = base_dwelling_pcdf_prices.fuel_cost
    base_sap = dwelling.sap_value
    base_co2 = dwelling.emissions

    # Now improve the dwelling
    for name, min_improvement, improve in IMPROVEMENTS:
        dwelling_pcdf_prices = DwellingResults(dwelling)
        dwelling_pcdf_prices.reduced_gains = False
        dwelling_pcdf_prices.use_pcdf_fuel_prices = True

        dwelling_regular_prices = DwellingResults(dwelling)
        dwelling_regular_prices.reduced_gains = False
        dwelling_regular_prices.use_pcdf_fuel_prices = False

        apply_previous_improvements(
                base_dwelling_pcdf_prices,
                dwelling_regular_prices,
                dwelling.improvement_results.improvement_effects)

        apply_previous_improvements(
                base_dwelling_pcdf_prices,
                dwelling_pcdf_prices,
                dwelling.improvement_results.improvement_effects)

        if not improve(base_dwelling_pcdf_prices, dwelling_pcdf_prices):
            continue

        improve(base_dwelling_pcdf_prices, dwelling_regular_prices)

        lookup_sap_tables(dwelling_pcdf_prices)
        worksheet.perform_full_calc(dwelling_pcdf_prices)
        worksheet.sap(dwelling_pcdf_prices)

        lookup_sap_tables(dwelling_regular_prices)
        worksheet.perform_full_calc(dwelling_regular_prices)
        worksheet.sap(dwelling_regular_prices)

        sap_improvement = dwelling_regular_prices.sap_value - base_sap

        if sap_improvement > min_improvement:
            dwelling.improvement_results.add(ImprovementResult(
                    name,
                    sap_improvement,
                    dwelling_pcdf_prices.fuel_cost - base_cost,
                    dwelling_regular_prices.emissions - base_co2))

            base_cost = dwelling_pcdf_prices.fuel_cost
            base_sap = dwelling_regular_prices.sap_value
            base_co2 = dwelling_regular_prices.emissions

    improved_dwelling = DwellingResults(dwelling)
    improved_dwelling.reduced_gains = False
    improved_dwelling.use_pcdf_fuel_prices = False

    for improvement in dwelling.improvement_results.improvement_effects:
        name, min_val, improve = [x for x in IMPROVEMENTS if x[0] == improvement.tag][0]
        improve(base_dwelling_pcdf_prices, improved_dwelling)

    lookup_sap_tables(improved_dwelling)

    worksheet.perform_full_calc(improved_dwelling)
    worksheet.sap(improved_dwelling)

    dwelling.report.build_report()
    # print improved_dwelling.report.print_report()

    dwelling.improved_results = improved_dwelling.results


class ImprovementResult:
    def __init__(self, tag, sap_change, cost_change, co2_change):
        self.tag = tag
        self.sap_change = sap_change
        self.co2_change = co2_change
        self.cost_change = cost_change


class ImprovementResults:
    def __init__(self):
        self.improvement_effects = []

    def add(self, i):
        self.improvement_effects.append(i)


def element_type_area(etype, els):
    return sum(e.area for e in els if e.element_type == etype)


def run_ter(input_dwelling):
    """
    Run the Target Energy Rating (TER) for the input dwelling.

    Args:
        input_dwelling:

    Returns:
          COPY of the dwelling with the TER results
          Assigns the .results to the input_dwelling.ter_results

    """
    # Note this previously wrapped dwelling in Dwelling Wrapper
    dwelling = DwellingResults(input_dwelling)

    dwelling.reduced_gains = True

    net_wall_area = element_type_area(HeatLossElementTypes.EXTERNAL_WALL,
                                      dwelling.heat_loss_elements)

    opaque_door_area = element_type_area(HeatLossElementTypes.OPAQUE_DOOR,
                                         dwelling.heat_loss_elements)

    window_area = sum(o.area for o in dwelling.openings if o.opening_type.roof_window is False)
    roof_window_area = sum(o.area for o in dwelling.openings if o.opening_type.roof_window is True)
    gross_wall_area = net_wall_area + window_area + opaque_door_area

    new_opening_area = min(dwelling.GFA * .25, gross_wall_area)
    new_window_area = max(new_opening_area - 1.85, 0)

    floor_area = element_type_area(HeatLossElementTypes.EXTERNAL_FLOOR,
                                   dwelling.heat_loss_elements)
    net_roof_area = element_type_area(HeatLossElementTypes.EXTERNAL_ROOF,
                                      dwelling.heat_loss_elements)
    roof_area = net_roof_area + roof_window_area

    heat_loss_elements = [
        HeatLossElement(
            area=gross_wall_area - new_window_area - 1.85,
            Uvalue=.35,
            is_external=True,
            element_type=HeatLossElementTypes.EXTERNAL_WALL
        ),
        HeatLossElement(
            area=1.85,
            Uvalue=2,
            is_external=True,
            element_type=HeatLossElementTypes.OPAQUE_DOOR
        ),
        HeatLossElement(
            area=floor_area,
            Uvalue=.25,
            is_external=True,
            element_type=HeatLossElementTypes.EXTERNAL_FLOOR
        ),
        HeatLossElement(
            area=roof_area,
            Uvalue=.16,
            is_external=True,
            element_type=HeatLossElementTypes.EXTERNAL_ROOF
        ),
        HeatLossElement(
            area=new_window_area,
            Uvalue=1. / (1. / 2 + .04),
            is_external=True,
            element_type=HeatLossElementTypes.GLAZING)
    ]

    dwelling.heat_loss_elements = heat_loss_elements

    ter_opening_type = OpeningType(
            glazing_type=GlazingTypes.DOUBLE,
            gvalue=.72,
            frame_factor=0.7,
            Uvalue=2,
            roof_window=False)

    new_openings = [Opening(
            area=new_window_area,
            orientation_degrees=90,
            opening_type=ter_opening_type)
    ]

    dwelling.openings = new_openings

    dwelling.thermal_mass_parameter = 250
    dwelling.overshading = OvershadingTypes.AVERAGE

    dwelling.Nshelteredsides = 2
    dwelling.Uthermalbridges = .11
    dwelling.ventilation_type = VentilationTypes.NATURAL
    dwelling.pressurisation_test_result = 10
    dwelling.Nchimneys = 0
    dwelling.Nflues = 0

    if input_dwelling.GFA > 80:
        dwelling.Nfansandpassivevents = 3
    else:
        dwelling.Nfansandpassivevents = 2

    dwelling.main_heating_type_code = 102
    dwelling.main_heating_pcdf_id = None
    dwelling.heating_emitter_type = HeatEmitters.RADIATORS
    dwelling.heating_emitter_type2 = None
    dwelling.main_heating_fraction = 1
    dwelling.main_heating_2_fraction = 0
    dwelling.main_sys_fuel = fuel_from_code(1)
    dwelling.main_heating_oil_pump_inside_dwelling = None
    dwelling.main_heating_2_oil_pump_inside_dwelling = None
    dwelling.control_type_code = 2106
    dwelling.sys1_has_boiler_interlock = True
    dwelling.sys1_load_compensator = None
    dwelling.central_heating_pump_in_heated_space = True
    dwelling.appendix_q_systems = None

    dwelling.has_hw_time_control = True
    dwelling.water_heating_type_code = 901
    dwelling.use_immersion_heater_summer = False
    dwelling.has_hw_cylinder = True
    dwelling.hw_cylinder_volume = 150
    dwelling.cylinder_in_heated_space = True
    dwelling.hw_cylinder_insulation_type = CylinderInsulationTypes.FOAM
    dwelling.hw_cylinder_insulation = 35
    dwelling.primary_pipework_insulated = False
    dwelling.has_cylinderstat = True
    dwelling.hwsys_has_boiler_interlock = True
    dwelling.measured_cylinder_loss = None
    dwelling.solar_collector_aperture = None
    dwelling.has_electric_shw_pump = False
    dwelling.solar_storage_combined_cylinder = False
    dwelling.wwhr_systems = None
    dwelling.fghrs = None
    dwelling.cylinder_is_thermal_store = False
    dwelling.thermal_store_type = None
    dwelling.sys1_sedbuk_2005_effy = None
    dwelling.sys1_sedbuk_2009_effy = None

    dwelling.sys1_delayed_start_thermostat = False

    dwelling.low_water_use = False
    dwelling.secondary_sys_fuel = dwelling.electricity_tariff
    dwelling.secondary_heating_type_code = 691
    dwelling.secondary_hetas_approved = False
    dwelling.low_energy_bulb_ratio = .3

    dwelling.cooled_area = 0

    # Need to make sure no summer immersion and no renewables

    lookup_sap_tables(dwelling)

    dwelling.main_sys_1.heating_effy_winter = 78 + .9
    dwelling.main_sys_1.heating_effy_summer = 78 - 9.2

    worksheet.perform_full_calc(dwelling)

    worksheet.ter(dwelling, input_dwelling.ter_fuel)

    dwelling.report.build_report()

    # Assign the TER results to the original dwelling
    input_dwelling.ter_results = dwelling.results
    return input_dwelling