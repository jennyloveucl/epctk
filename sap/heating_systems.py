"""
Defining heating systems

Encorporates parts of SAP main body and appendicies


"""
from sap.appendix_f import appendix_f_cpsu_on_peak
from sap.fuels import ELECTRICITY_7HR, ELECTRICITY_10HR
from sap.sap_types import HeatingTypes, ImmersionTypes
from .appendix_j import solid_fuel_boiler_from_pcdf
from .appendix_g import configure_combi_loss
from .appendix_n import heat_pump_from_pcdf, micro_chp_from_pcdf
from .heating_system_types import HeatingSystem
from .pcdf import (get_boiler, get_solid_fuel_boiler, get_twin_burner_cooker_boiler, get_heat_pump, get_microchp)
from .sap_tables import (combi_loss_instant_without_keep_hot, combi_loss_instant_with_timed_heat_hot,
    combi_loss_instant_with_untimed_heat_hot, USE_TABLE_4D_FOR_RESPONSIVENESS)
from .sap_types import HeatingTypes, ThermalStoreTypes, CylinderInsulationTypes


# Table 12a
# Table 13


def pcdf_heating_system(dwelling, pcdf_id,
                        fuel, use_immersion_in_summer):
    """
    Get the PCDF heating system for the dwelling

    Try each type in turn until we get a heating system that is not None

    :param dwelling:
    :param pcdf_id:
    :param fuel:
    :param use_immersion_in_summer:
    :return:
    """
    pcdf_data = get_boiler(pcdf_id)
    if pcdf_data is not None:
        return gas_boiler_from_pcdf(dwelling, pcdf_data, fuel, use_immersion_in_summer)

    pcdf_data = get_solid_fuel_boiler(pcdf_id)
    if pcdf_data is not None:
        return solid_fuel_boiler_from_pcdf(pcdf_data, fuel, use_immersion_in_summer)

    pcdf_data = get_twin_burner_cooker_boiler(pcdf_id)
    if pcdf_data is not None:
        return twin_burner_cooker_boiler_from_pcdf(pcdf_data, fuel, use_immersion_in_summer)

    pcdf_data = get_heat_pump(pcdf_id)
    if pcdf_data is not None:
        return heat_pump_from_pcdf(dwelling, pcdf_data, fuel, use_immersion_in_summer)

    pcdf_data = get_microchp(pcdf_id)
    if pcdf_data is not None:
        return micro_chp_from_pcdf(dwelling, pcdf_data, fuel, use_immersion_in_summer)


def gas_boiler_from_pcdf(dwelling, pcdf_data, fuel, use_immersion_in_summer):
    if pcdf_data['main_type'] == "Combi":
        system_type = HeatingTypes.combi
    elif pcdf_data['main_type'] == "CPSU":
        system_type = HeatingTypes.cpsu
    else:
        system_type = HeatingTypes.regular_boiler

    sys = HeatingSystem(system_type,
                        pcdf_data['winter_effy'],
                        pcdf_data['summer_effy'],
                        False,  # summer immersion
                        pcdf_data['fan_assisted_flue'] == 'True',
                        True,  # ch pump
                        -1,
                        0.1,
                        fuel)  # !!! Assumes 10% secondary fraction

    # !!!
    sys.has_warm_air_fan = False
    sys.sap_appendixD_eqn = pcdf_data['sap_appendixD_eqn']
    sys.is_condensing = pcdf_data['condensing']

    if pcdf_data['subsidiary_type'] == "with integral PFGHRD":
        if (pcdf_data['subsidiary_type_table'] == "" and
                    pcdf_data['subsidiary_type_index'] == ""):
            # integral PFGHRD, performance data included in boilerl data
            assert not dwelling.get('fghrs')
        else:
            if (dwelling.get('fghrs') and
                        dwelling.fghrs is None):
                # inputs expliticly say there is no fghrs, so don't
                # add one even if boiler specifies one
                pass
            else:
                if dwelling.get('fghrs'):
                    assert dwelling.fghrs['pcdf_id'] == pcdf_data['subsidiary_type_index']
                else:
                    dwelling.fghrs = dict(pcdf_id=pcdf_data['subsidiary_type_index'])

    if pcdf_data['storage_type'] != "Unknown":
        # Shouldn't have cylinder data specified if we are going to
        # use pcdf cylinder info
        assert not dwelling.get("hw_cylinder_volume")

    if pcdf_data['main_type'] == 'Regular':
        # !!! Also need to allow this for table 4a systems?
        if dwelling.get('cylinder_is_thermal_store'):
            if dwelling.thermal_store_type == ThermalStoreTypes.HW_ONLY:
                sys.table2b_row = 6
            else:
                sys.table2b_row = 7
            dwelling.has_cylinderstat = True
        else:
            sys.table2b_row = 2  # !!! Assumes not electric
    elif pcdf_data['main_type'] == 'Combi':
        # !!! introduce a type for storage types
        if pcdf_data['storage_type'] in ['storage combi with primary store', 'storage combi with secondary store']:
            # !!! Should only do this if combi is the hw system - this
            # !!! check for having a defined ins type works for now,
            # !!! but will need improving
            if not dwelling.get('hw_cylinder_insulation_type'):
                dwelling.hw_cylinder_volume = pcdf_data["store_boiler_volume"]
                dwelling.hw_cylinder_insulation = pcdf_data["store_insulation_mms"]
                dwelling.hw_cylinder_insulation_type = CylinderInsulationTypes.FOAM
                # Force calc to use the data from pcdf, don't use a user entered cylinder loss
                dwelling.measured_cylinder_loss = None

        if pcdf_data['storage_type'] == 'storage combi with primary store':
            sys.table2b_row = 3
            dwelling.has_cylinderstat = True
        elif pcdf_data['storage_type'] == 'storage combi with secondary store':
            sys.table2b_row = 4
            dwelling.has_cylinderstat = True

        if not 'keep_hot_facility' in pcdf_data or pcdf_data['keep_hot_facility'] == 'None':
            sys.has_no_keep_hot = True
            sys.table3arow = combi_loss_instant_without_keep_hot
        elif pcdf_data['keep_hot_timer']:
            sys.table3arow = combi_loss_instant_with_timed_heat_hot
            if pcdf_data['keep_hot_facility'] == "elec" or pcdf_data[
                'keep_hot_facility'] == "gas/oil and elec":  # !!! or mixed?
                sys.keep_hot_elec_consumption = 600
        else:
            sys.table3arow = combi_loss_instant_with_untimed_heat_hot
            if pcdf_data['keep_hot_facility'] == "elec" or pcdf_data[
                'keep_hot_facility'] == "gas/oil and elec":  # !!! or mixed?
                sys.keep_hot_elec_consumption = 900

    elif pcdf_data['main_type'] == 'CPSU':
        sys.table2b_row = 7  # !!! Assumes gas-fired
        dwelling.has_cylinderstat = True
        sys.cpsu_Tw = dwelling.cpsu_Tw
        sys.cpsu_not_in_airing_cupboard = dwelling.get('cpsu_not_in_airing_cupboard', False)

    else:
        # !!! What about other table rows?
        raise ValueError("Unknown system type")

    if sys.system_type == HeatingTypes.combi:
        configure_combi_loss(dwelling, sys, pcdf_data)
    # !!! Assumes gas/oil boiler
    sys.responsiveness = USE_TABLE_4D_FOR_RESPONSIVENESS
    return sys


def twin_burner_cooker_boiler_from_pcdf(pcdf_data, fuel,
                                        use_immersion_in_summer):
    winter_effy = pcdf_data['winter_effy']
    summer_effy = pcdf_data['summer_effy']

    sys = HeatingSystem(HeatingTypes.regular_boiler,  # !!!
                        winter_effy,
                        summer_effy,
                        summer_immersion=use_immersion_in_summer,
                        has_flue_fan=False,  # !!!
                        has_ch_pump=True,
                        table2b_row=2,  # !!! Solid fuel boilers can only have indirect boiler?
                        default_secondary_fraction=0.1,  # !!! Assumes 10% secondary fraction
                        fuel=fuel)

    sys.range_cooker_heat_required_scale_factor = 1 - (
        pcdf_data['case_loss_at_full_output'] / pcdf_data['full_output_power'])

    # !!! Assumes we have a heat emitter - is that always the case?
    sys.responsiveness = USE_TABLE_4D_FOR_RESPONSIVENESS

    # !!!
    sys.has_warm_air_fan = False
    return sys


def space_heat_on_peak_fraction(sys, dwelling):
    if sys.system_type == HeatingTypes.off_peak_only:
        return 0

    elif sys.system_type == HeatingTypes.integrated_system:
        assert sys.fuel == ELECTRICITY_7HR
        return .2

    elif sys.system_type == HeatingTypes.storage_heater:
        return 0

    elif sys.system_type == HeatingTypes.cpsu:
        return appendix_f_cpsu_on_peak(sys, dwelling)

    elif sys.system_type == HeatingTypes.electric_boiler:
        if sys.fuel == ELECTRICITY_7HR:
            return 0.9
        elif sys.fuel == ELECTRICITY_10HR:
            return .5
        else:
            return 1

    elif sys.system_type in [HeatingTypes.pcdf_heat_pump,
                             HeatingTypes.microchp]:
        return .8

    elif sys.system_type == HeatingTypes.heat_pump:
        return 0.6
    # !!! underfloor heating
    # !!! ground source heat pump
    # !!! air source heat pump
    # !!! other direct acting heating (incl secondary)
    else:
        if sys.fuel == ELECTRICITY_10HR:
            return .5
        else:
            return 1


def heating_fuel_cost(sys, dwelling):
    if sys.fuel.is_electric:
        on_peak = space_heat_on_peak_fraction(sys, dwelling)
        return sys.fuel.unit_price(on_peak)
    else:
        return sys.fuel.unit_price()


def dhw_fuel_cost(dwelling):
    if dwelling.water_sys.fuel.is_electric and dwelling.get('immersion_type') is not None:
        # !!! Are there other places that should use non-solar cylinder volume?
        non_solar_cylinder_volume = dwelling.hw_cylinder_volume - (
            dwelling.solar_dedicated_storage_volume
            if dwelling.get('solar_dedicated_storage_volume')
            else 0)
        on_peak = immersion_on_peak_fraction(dwelling.Nocc,
                                             dwelling.electricity_tariff,
                                             non_solar_cylinder_volume,
                                             dwelling.immersion_type)
        return dwelling.water_sys.fuel.unit_price(on_peak)

    elif dwelling.water_sys.fuel.is_electric:
        on_peak = dhw_on_peak_fraction(dwelling.water_sys, dwelling)
        return dwelling.water_sys.fuel.unit_price(on_peak)

    else:
        return dwelling.water_sys.fuel.unit_price()


def dhw_on_peak_fraction(water_sys, dwelling):
    """
    Function equivalent to Table 12a, describing the fraction of district hot water on
    peak
    :param water_sys: type of hot water system
    :param dwelling:
    :return:
    """
    # !!! Need to complete this table
    if water_sys.system_type == HeatingTypes.cpsu:
        return appendix_f_cpsu_on_peak(water_sys, dwelling)
    elif water_sys.system_type == HeatingTypes.heat_pump:
        # !!! Need off-peak immersion option
        return .7
    elif water_sys.system_type in [HeatingTypes.pcdf_heat_pump,
                                   HeatingTypes.microchp]:
        return .7
    else:
        return water_sys.fuel.general_elec_on_peak_fraction


def immersion_on_peak_fraction(N_occ, elec_tariff, cylinder_volume, immersion_type):
    """

    :param N_occ: number of occupants
    :param elec_tariff:
    :param cylinder_volume:
    :param immersion_type:
    :return:
    """
    if elec_tariff == ELECTRICITY_7HR:
        if immersion_type == ImmersionTypes.SINGLE:
            return max(0, ((14530 - 762 * N_occ) / cylinder_volume - 80 + 10 * N_occ) / 100)
        else:
            assert immersion_type == ImmersionTypes.DUAL
            return max(0, ((6.8 - 0.024 * cylinder_volume) * N_occ + 14 - 0.07 * cylinder_volume) / 100)
    elif elec_tariff == ELECTRICITY_10HR:
        if immersion_type == ImmersionTypes.SINGLE:
            return max(0, ((14530 - 762 * N_occ) / (1.5 * cylinder_volume) - 80 + 10 * N_occ) / 100)
        else:
            assert immersion_type == ImmersionTypes.DUAL
            return max(0, ((6.8 - 0.036 * cylinder_volume) * N_occ + 14 - 0.105 * cylinder_volume) / 100)
    else:
        return 1