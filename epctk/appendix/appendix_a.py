"""
Main and secondary heating systems
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The main heating system is that which heats the largest proportion of dwelling.
It is a heating system which is not usually based on individual room heaters
(although it can be), and often provides hot water as well as space heating.
Main heating systems are either identified via the Product Characteristics Database
or are categorised on the basis of the generic types in Tables 4a and 4b.


A2.1 Identifying the main system

    1. If there is a central system that provides both space and water heating and
        it is capable of heating at least 30% of the dwelling, select that system
        as the main heating system. If there is no system that provides both space
        and water heating, then select the system that has the capability of heating
        the greatest part of the dwelling. For this purpose only habitable rooms should
        be considered (i.e. ignore heaters in non-habitable rooms).
    2. If there is still doubt about which system should be selected as the main system,
       select the system that supplies useful heat to the dwelling at lowest cost
       (obtained by dividing fuel cost by conversion efficiency).

"""
from ..elements import HeatingTypes, HeatingSystem, SecondarySystem
from ..fuels import ELECTRICITY_STANDARD
from ..tables import (system_efficiency, system_type_from_sap_code, combi_loss_table_3a, TABLE_4A, TABLE_4B,
                      get_4a_system)


def apply_appendix_a():
    """
    .. todo::
     Move the main logic relating to appendix A from wherever it is now into this function!

    A4 Description of the dwelling's heating systems and software implementation

    a) If there is no heating system, assign electric heaters as the main
       system heating all rooms (no secondary system).

    b) If 25% or less of the habitable rooms are heated and their heating is by
       a room heater (not electric), assign electric heaters as the main system
       and the identified room heaters as the secondary system, applying the
       secondary fraction according to Table 11 for electric room heaters as the
       main system.

       If two main heating systems have been identified (e.g. a gas fire in one room,
       a coal fire in another room, plus 6 unheated habitable rooms) then:

        - assign electric heaters as main system1
        - assign the room heater entered as main system1 as the secondary system
        - main system2 remains as it is
        - set the fraction of heat from main system2 equal to heated habitable rooms
          divided by total habitable rooms

    c) Otherwise if there are any unheated habitable rooms and no secondary system
       has been identified, undertake the calculation with electric secondary heating
      (portable electric heaters).

    d) If any fixed secondary heater has been identified, the calculation proceeds
       with the identified secondary heater, whether or not there are unheated habitable rooms.

    e) If there are no unheated habitable rooms and no fixed secondary heater
       in a habitable room, undertake the calculation with no secondary heating.

    f) An assumed heater, where main or secondary, is an electric portable heater.
       In case of main heating it does not have thermostatic control.


    Table 11 gives the fraction of the heating that is assumed to be supplied by the secondary system.
    The treatment of secondary systems is not affected by any control options for the secondary system.

    """
    pass


def _secondary_code_from_main(main_type_code, main_fuel):
    # TODO: original code would let this part OVERRIDE the explcit heating code,
    # but here we EITHER have heating code OR infer from main heating

    # Check code in range 401-408 OR code in range 421-425 AND fuel is not ELECTRICITY_STANDARD
    if main_type_code is not None and main_type_code != 'community' and (
                (401 <= main_type_code <= 408) or
                ((421 <= main_type_code <= 425) and
                         main_fuel != ELECTRICITY_STANDARD)):
        # TODO Does 24 hour tariff count as being offpeak?
        return 693
    else:
        return None


def configure_secondary_system(dwelling, force_secondary_heating=False):
    # TODO Need to apply the rules from A4 here - need to do this
    # before fraction_of_heat_from_main is set.  Also back boiler
    # should have secondary system - see section 9.2.8
    use_immersion = dwelling.get('use_immersion_heater_summer', False)

    if dwelling.get('secondary_sys_manuf_effy'):
        dwelling.secondary_sys = get_manuf_data_secondary_system(dwelling.secondary_sys_fuel,
                                                                 dwelling.secondary_sys_manuf_effy,
                                                                 use_immersion)
        return

    heating_code = dwelling.get('secondary_heating_type_code')
    hetas_approved = dwelling.get('secondary_hetas_approved')
    electricity_tariff = dwelling.electricity_tariff

    if heating_code is None:
        fuel = dwelling.electricity_tariff
        heating_code = _secondary_code_from_main(dwelling.get('main_heating_type_code'), dwelling.main_sys_fuel)

        if heating_code is None:
            if force_secondary_heating:
                heating_code = 693
            else:
                return

    else:
        fuel = dwelling.secondary_sys_fuel

    dwelling.secondary_sys = get_4a_secondary_system(fuel, heating_code, electricity_tariff, use_immersion,
                                                     hetas_approved)

    dwelling.secondary_heating_type_code = dwelling.secondary_sys.sap_code
    dwelling.secondary_sys_fuel = dwelling.secondary_sys.fuel


def sap_table_heating_system(dwelling, system_code, fuel,
                             use_immersion_in_summer, hetas_approved):
    """
    Loads a HeatingSystem definition from SAP Table 4a if available, otherwise
    from Table 4b

    Args:
        dwelling:
        system_code:
        fuel:
        use_immersion_in_summer:
        hetas_approved:

    Return:
        HeatingSystem: A heating system object with data loaded from the appropriate SAP table
    """
    if system_code in TABLE_4A:
        system = get_4a_main_system(dwelling, system_code, fuel,
                                    use_immersion_in_summer, hetas_approved)
    else:
        system = get_4b_main_system(dwelling, system_code, fuel,
                                    use_immersion_in_summer)
    return system


def has_ch_pump(dwelling):
    return (dwelling.get('heating_emitter_type', False) or
            dwelling.get('heating_emitter_type2', False))


def get_4a_main_system(dwelling, system_code, fuel,
                       use_immersion_in_summer, hetas_approved):
    """
    Get the main heating system according to Table 4a for the given dwelling

    Args:
        dwelling:
        system_code:
        fuel:
        use_immersion_in_summer:
        hetas_approved:

    Returns:
        HeatingSystem: heating system configured according to Table 4A
    """
    system_data = get_4a_system(dwelling.electricity_tariff, system_code)

    if hetas_approved and system_data['effy_hetas'] > 0:
        effy = system_data["effy_hetas"]
    else:
        effy = system_efficiency(system_data, fuel)

    system = HeatingSystem(system_type_from_sap_code(system_code, system_data),
                           effy,
                           effy,
                           use_immersion_in_summer,
                           system_data['flue_fan'] == 'TRUE',
                           has_ch_pump(dwelling),
                           system_data['table2b_row'],
                           system_data['fraction_of_heat_from_secondary'],
                           fuel)

    system.has_warm_air_fan = system_data['warm_air_fan'] == "TRUE"
    system.responsiveness = system_data['responsiveness']

    if system_data['water_effy'] != "same":
        system.water_effy = float(system_data['water_effy'])

    if system.system_type in [HeatingTypes.combi,
                              HeatingTypes.storage_combi]:
        system.combi_loss = combi_loss_table_3a(dwelling, system)

    elif system.system_type == HeatingTypes.cpsu:
        system.cpsu_Tw = dwelling.cpsu_Tw
        system.cpsu_not_in_airing_cupboard = dwelling.get('cpsu_not_in_airing_cupboard')

    return system


def get_4a_secondary_system(fuel, sap_type_code, electricity_tariff, use_immersion_heater_summer,
                            hetas_approved):
    """
    Get the secondary heating system according to Table 4a for the
    given dwelling

    Args:
        sap_type_code:
        electricity_tariff:
        use_immersion_heater_summer:
        hetas_approved:

    Returns:
        SecondarySystem: Secondary heating system configured from Table 4a
    """
    system_data = get_4a_system(electricity_tariff, sap_type_code)

    if hetas_approved and system_data['effy_hetas'] > 0:
        effy = system_data["effy_hetas"]
    else:
        effy = system_efficiency(system_data, fuel)

    sys = SecondarySystem(system_type_from_sap_code(sap_type_code, system_data), fuel, effy,
                          use_immersion_heater_summer, sap_code=sap_type_code)

    sys.table2b_row = system_data['table2b_row']

    if system_data['water_effy'] != "same" and system_data['water_effy'] != "":
        sys.water_effy = float(system_data['water_effy'])

    return sys


def get_4b_main_system(dwelling, system_code, fuel, use_immersion_in_summer):
    """
    Get the secondary heating system according to Table 4b for the
    given dwelling

    Args:
        dwelling (Dwelling):
        system_code:
        fuel:
        use_immersion_in_summer:

    Returns:
        SecondarySystem: Secondary heating system configured from Table 4b
    """
    system_data = TABLE_4B[system_code]
    system = HeatingSystem(system_type_from_sap_code(system_code, system_data),
                           system_data['effy_winter'],
                           system_data['effy_summer'],
                           use_immersion_in_summer,
                           system_data['flue_fan'] == 'TRUE',
                           has_ch_pump(dwelling),
                           system_data['table2b_row'],
                           system_data['fraction_of_heat_from_secondary'],
                           fuel)

    system.responsiveness = system_data['responsiveness']
    system.is_condensing = system_data['condensing']

    if system.system_type in [HeatingTypes.combi, HeatingTypes.storage_combi]:
        system.combi_loss = combi_loss_table_3a(dwelling, system)

    elif system.system_type == HeatingTypes.cpsu:
        system.cpsu_not_in_airing_cupboard = dwelling.get('cpsu_not_in_airing_cupboard', False)

    return system


def get_manuf_data_secondary_system(fuel, effy, use_immersion_heater_summer):
    sys = SecondarySystem(HeatingTypes.misc, fuel, effy, use_immersion_heater_summer)

    # sys.table2b_row=system_data['table2b_row']
    return sys
