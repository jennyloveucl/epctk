from sap.pcdf import VentilationTypes
from .dwelling import DwellingResultsWrapper
from .sap_tables import CylinderInsulationTypes, GlazingTypes, do_sap_table_lookups, OvershadingTypes, HeatEmitters, \
    fuel_from_code, HeatingSystem, PVOvershading, hw_volume_factor
from . import worksheet


def perform_demand_calc(dwelling):
    worksheet.ventilation(dwelling)
    worksheet.heat_loss(dwelling)
    worksheet.hot_water_use(dwelling)
    worksheet.internal_heat_gain(dwelling)
    worksheet.solar(dwelling)
    worksheet.heating_requirement(dwelling)
    worksheet.cooling_requirement(dwelling)
    worksheet.water_heater_output(dwelling)


def perform_full_calc(dwelling):
    perform_demand_calc(dwelling)
    worksheet.systems(dwelling)
    worksheet.pv(dwelling)
    worksheet.wind_turbines(dwelling)
    worksheet.hydro(dwelling)
    worksheet.chp(dwelling)
    worksheet.fuel_use(dwelling)



def run_sap(input_dwelling):
    """
    Run SAP on the input dwelling
    :param input_dwelling:
    :return:
    """
    dwelling = DwellingResultsWrapper(input_dwelling)
    dwelling.reduced_gains = False

    do_sap_table_lookups(dwelling)
    perform_full_calc(dwelling)
    worksheet.sap(dwelling)
    dwelling.report.build_report()

    input_dwelling.er_results = dwelling.results


def run_fee(input_dwelling):
    dwelling = DwellingResultsWrapper(input_dwelling)
    dwelling.reduced_gains = True

    dwelling.cooled_area = input_dwelling.GFA
    dwelling.low_energy_bulb_ratio = 1
    dwelling.ventilation_type = VentilationTypes.NATURAL
    dwelling.water_heating_type_code = 907
    dwelling.fghrs = None

    if input_dwelling.GFA <= 70:
        dwelling.Nfansandpassivevents = 2
    elif input_dwelling.GFA <= 100:
        dwelling.Nfansandpassivevents = 3
    else:
        dwelling.Nfansandpassivevents = 4

    if dwelling.overshading == OvershadingTypes.VERY_LITTLE:
        dwelling.overshading = OvershadingTypes.AVERAGE

    dwelling.main_heating_pcdf_id = None
    dwelling.main_heating_type_code = 191
    dwelling.main_sys_fuel = fuel_from_code(1)
    dwelling.heating_emitter_type = HeatEmitters.RADIATORS
    dwelling.control_type_code = 2106
    dwelling.sys1_delayed_start_thermostat = False
    dwelling.use_immersion_heater_summer = False
    dwelling.immersion_type = None
    dwelling.solar_collector_aperture = None
    dwelling.cylinder_is_thermal_store = False
    dwelling.thermal_store_type = None
    dwelling.sys1_sedbuk_2005_effy = None
    dwelling.sys1_sedbuk_2009_effy = None

    # Don't really need to set these, but sap_tables isn't happy if we don't
    dwelling.cooling_packaged_system = True
    dwelling.cooling_energy_label = "A"
    dwelling.cooling_compressor_control = ""
    dwelling.water_sys_fuel = dwelling.electricity_tariff
    dwelling.main_heating_fraction = 1
    dwelling.main_heating_2_fraction = 0

    do_sap_table_lookups(dwelling)

    dwelling.pump_gain = 0
    dwelling.heating_system_pump_gain = 0

    perform_demand_calc(dwelling)
    worksheet.fee(dwelling)
    dwelling.report.build_report()

    input_dwelling.fee_results = dwelling.results


def run_der(input_dwelling):
    dwelling = DwellingResultsWrapper(input_dwelling)
    dwelling.reduced_gains = True

    if dwelling.overshading == OvershadingTypes.VERY_LITTLE:
        dwelling.overshading = OvershadingTypes.AVERAGE

    do_sap_table_lookups(dwelling)
    perform_full_calc(dwelling)
    worksheet.der(dwelling)
    dwelling.report.build_report()

    input_dwelling.der_results = dwelling.results
    if (dwelling.main_sys_fuel.is_mains_gas or
            (hasattr(dwelling, 'main_sys_2_fuel') and
                 dwelling.main_sys_2_fuel.is_mains_gas)):
        input_dwelling.ter_fuel = fuel_from_code(1)
    elif sum(dwelling.Q_main_1) >= sum(dwelling.Q_main_2):
        input_dwelling.ter_fuel = dwelling.main_sys_fuel
    else:
        input_dwelling.ter_fuel = dwelling.main_sys_2_fuel


def element_type_area(etype, els):
    return sum(e.area for e in els if e.element_type == etype)


def run_ter(input_dwelling):
    dwelling = DwellingResultsWrapper(input_dwelling)

    dwelling.reduced_gains = True

    net_wall_area = element_type_area(worksheet.HeatLossElementTypes.EXTERNAL_WALL,
                                      dwelling.heat_loss_elements)
    opaque_door_area = element_type_area(worksheet.HeatLossElementTypes.OPAQUE_DOOR,
                                         dwelling.heat_loss_elements)
    window_area = sum(o.area for o in dwelling.openings if o.opening_type.roof_window == False)
    roof_window_area = sum(o.area for o in dwelling.openings if o.opening_type.roof_window == True)
    gross_wall_area = net_wall_area + window_area + opaque_door_area

    new_opening_area = min(dwelling.GFA * .25, gross_wall_area)
    new_window_area = max(new_opening_area - 1.85, 0)

    floor_area = element_type_area(worksheet.HeatLossElementTypes.EXTERNAL_FLOOR,
                                   dwelling.heat_loss_elements)
    net_roof_area = element_type_area(worksheet.HeatLossElementTypes.EXTERNAL_ROOF,
                                      dwelling.heat_loss_elements)
    roof_area = net_roof_area + roof_window_area

    new_heat_loss_elements = []
    new_heat_loss_elements.append(worksheet.HeatLossElement(
        area=gross_wall_area - new_window_area - 1.85,
        Uvalue=.35,
        is_external=True,
        element_type=worksheet.HeatLossElementTypes.EXTERNAL_WALL,
    ))
    new_heat_loss_elements.append(worksheet.HeatLossElement(
        area=1.85,
        Uvalue=2,
        is_external=True,
        element_type=worksheet.HeatLossElementTypes.OPAQUE_DOOR,
    ))
    new_heat_loss_elements.append(worksheet.HeatLossElement(
        area=floor_area,
        Uvalue=.25,
        is_external=True,
        element_type=worksheet.HeatLossElementTypes.EXTERNAL_FLOOR,
    ))
    new_heat_loss_elements.append(worksheet.HeatLossElement(
        area=roof_area,
        Uvalue=.16,
        is_external=True,
        element_type=worksheet.HeatLossElementTypes.EXTERNAL_ROOF,
    ))
    new_heat_loss_elements.append(worksheet.HeatLossElement(
        area=new_window_area,
        Uvalue=1. / (1. / 2 + .04),
        is_external=True,
        element_type=worksheet.HeatLossElementTypes.GLAZING,
    ))

    dwelling.heat_loss_elements = new_heat_loss_elements

    ter_opening_type = worksheet.OpeningType(
        glazing_type=GlazingTypes.DOUBLE,
        gvalue=.72,
        frame_factor=0.7,
        Uvalue=2,
        roof_window=False)

    new_openings = [worksheet.Opening(
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

    do_sap_table_lookups(dwelling)
    dwelling.main_sys_1.heating_effy_winter = 78 + .9
    dwelling.main_sys_1.heating_effy_summer = 78 - 9.2

    perform_full_calc(dwelling)
    worksheet.ter(dwelling, input_dwelling.ter_fuel)
    dwelling.report.build_report()
    input_dwelling.ter_results = dwelling.results


def apply_low_energy_lighting(base, d):
    if ((hasattr(d, 'low_energy_bulb_ratio') and d.low_energy_bulb_ratio == 1) or
                d.lighting_outlets_low_energy == d.lighting_outlets_total):
        return False

    d.low_energy_bulb_ratio = 1
    return True


def needs_separate_solar_cylinder(base, d):
    if base.water_sys.system_type in [
        HeatingSystem.TYPES.cpsu,
        HeatingSystem.TYPES.combi,
        HeatingSystem.TYPES.storage_combi,
        HeatingSystem.TYPES.heat_pump,
        HeatingSystem.TYPES.pcdf_heat_pump,
    ]:
        return True
    if (hasattr(base, 'instantaneous_pou_water_heating') and
            base.instantaneous_pou_water_heating):
        return True
    if (base.water_sys.system_type == HeatingSystem.TYPES.community
        and not hasattr(d, 'hw_cylinder_volume')):
        return True
    if (base.water_sys.system_type == HeatingSystem.TYPES.microchp
        and base.water_sys.has_integral_store):
        return True

    return False


def apply_solar_hot_water(base, d):
    if d.is_flat:
        return False
    if hasattr(d, 'solar_collector_aperture') and d.solar_collector_aperture > 0:
        return False
    d.solar_collector_aperture = 3
    d.collector_zero_loss_effy = .7
    d.collector_heat_loss_coeff = 1.8
    d.collector_orientation = 180.
    d.collector_pitch = 30.
    d.collector_overshading = PVOvershading.MODEST
    d.has_electric_shw_pump = True
    d.solar_dedicated_storage_volume = 75.

    if needs_separate_solar_cylinder(base, d):
        d.solar_storage_combined_cylinder = False
    else:
        assert d.hw_cylinder_volume > 0
        d.solar_storage_combined_cylinder = True
        if d.hw_cylinder_volume < 190 and hasattr(d, 'measured_cylinder_loss'):
            old_vol_fac = hw_volume_factor(d.hw_cylinder_volume)
            new_vol_fac = hw_volume_factor(190)
            d.measured_cylinder_loss *= new_vol_fac * 190 / (old_vol_fac * d.hw_cylinder_volume)
            d.hw_cylinder_volume = 190
        else:
            d.hw_cylinder_volume = max(d.hw_cylinder_volume, 190.)

    return True


def apply_pv(base, d):
    if d.is_flat:
        return False
    if hasattr(d, 'photovoltaic_systems') and len(d.photovoltaic_systems) > 0:
        return False

    pv_system = dict(
        kWp=2.5,
        pitch=30,
        orientation=180,
        overshading_category=PVOvershading.MODEST
    )
    d.photovoltaic_systems = [pv_system, ]
    return True


def apply_wind(base, d):
    if d.is_flat:
        return False
    if hasattr(d, 'N_wind_turbines') and d.N_wind_turbines > 0:
        return False
    d.N_wind_turbines = 1
    d.wind_turbine_rotor_diameter = 2.0
    d.wind_turbine_hub_height = 2.0
    return True


IMPROVEMENTS = [
    ("E", .45, apply_low_energy_lighting),
    ("N", .95, apply_solar_hot_water),
    ("U", .95, apply_pv),
    ("V", .95, apply_wind),
]


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


def apply_previous_improvements(base, target, previous):
    for improvement in previous:
        name, min_val, improve = [x for x in IMPROVEMENTS if x[0] == improvement.tag][0]
        improve(base, target)
        improve(base, target)


def run_improvements(dwelling):
    # Need to run the dwelling twice: once with pcdf fuel prices to
    # get cost chage, once with normal SAP fuel prices to get change
    # in SAP rating
    base_dwelling_pcdf_prices = DwellingResultsWrapper(dwelling)
    base_dwelling_pcdf_prices.reduced_gains = False
    base_dwelling_pcdf_prices.use_pcdf_fuel_prices = True

    do_sap_table_lookups(base_dwelling_pcdf_prices)
    perform_full_calc(base_dwelling_pcdf_prices)
    worksheet.sap(base_dwelling_pcdf_prices)


    dwelling.improvement_results = ImprovementResults()

    base_cost = base_dwelling_pcdf_prices.results['fuel_cost']
    base_sap = dwelling.er_results['sap_value']
    base_co2 = dwelling.er_results['emissions']
    for name, min_improvement, improve in IMPROVEMENTS:
        wrapped_dwelling_pcdf_prices = DwellingResultsWrapper(dwelling)
        wrapped_dwelling_pcdf_prices.reduced_gains = False
        wrapped_dwelling_pcdf_prices.use_pcdf_fuel_prices = True

        wrapped_dwelling = DwellingResultsWrapper(dwelling)
        wrapped_dwelling.reduced_gains = False
        wrapped_dwelling.use_pcdf_fuel_prices = False

        apply_previous_improvements(
            base_dwelling_pcdf_prices,
            wrapped_dwelling,
            dwelling.improvement_results.improvement_effects)
        apply_previous_improvements(
            base_dwelling_pcdf_prices,
            wrapped_dwelling_pcdf_prices,
            dwelling.improvement_results.improvement_effects)

        if not improve(base_dwelling_pcdf_prices, wrapped_dwelling_pcdf_prices):
            continue

        improve(base_dwelling_pcdf_prices, wrapped_dwelling)

        do_sap_table_lookups(wrapped_dwelling_pcdf_prices)
        perform_full_calc(wrapped_dwelling_pcdf_prices)
        worksheet.sap(wrapped_dwelling_pcdf_prices)

        do_sap_table_lookups(wrapped_dwelling)
        perform_full_calc(wrapped_dwelling)
        worksheet.sap(wrapped_dwelling)

        sap_improvement = wrapped_dwelling.sap_value - base_sap
        if sap_improvement > min_improvement:
            dwelling.improvement_results.add(ImprovementResult(
                name,
                sap_improvement,
                wrapped_dwelling_pcdf_prices.fuel_cost - base_cost,
                wrapped_dwelling.emissions - base_co2))

            base_cost = wrapped_dwelling_pcdf_prices.fuel_cost
            base_sap = wrapped_dwelling.sap_value
            base_co2 = wrapped_dwelling.emissions

    improved_dwelling = DwellingResultsWrapper(dwelling)
    improved_dwelling.reduced_gains = False
    improved_dwelling.use_pcdf_fuel_prices = False
    for improvement in dwelling.improvement_results.improvement_effects:
        name, min_val, improve = [x for x in IMPROVEMENTS if x[0] == improvement.tag][0]
        improve(base_dwelling_pcdf_prices, improved_dwelling)

    do_sap_table_lookups(improved_dwelling)
    perform_full_calc(improved_dwelling)
    worksheet.sap(improved_dwelling)

    dwelling.report.build_report()
    # print improved_dwelling.report.print_report()

    dwelling.improved_results = improved_dwelling.results

