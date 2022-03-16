# imports
import json
import warnings
from ebus_toolbox.consumption import Consumption
from ebus_toolbox.schedule import Schedule
from ebus_toolbox.trip import Trip
from ebus_toolbox import report  # , optimizer
# SPICE EV SIMULATE
import simulate as spice_ev


def simulate(args):
    """Simulate the given scenario and eventually optimize for given metric(s).

    :param args: Configuration arguments specified in config files contained in configs directory.
    :type args: argparse.Namespace
    """
    try:
        with open(args.vehicle_types) as f:
            vehicle_types = json.load(f)
    except FileNotFoundError:
        warnings.warn("Invalid path for vehicle type JSON. Using default types from EXAMPLE dir.")
        with open("data/examples/vehicle_types.json") as f:
            vehicle_types = json.load(f)

    schedule = Schedule.from_csv(args.input_schedule, vehicle_types)
    # setup consumption calculator that can be accessed by all trips
    Trip.consumption = Consumption(vehicle_types)
    # filter trips according to args
    schedule.filter_rotations()
    schedule.calculate_consumption()
    schedule.set_charging_type(preferred_ct=args.preferred_charging_type)
    # initialize optimizer
    i = 0
    while(True):
        # construct szenario and simulate in spice ev until optimizer is happy
        # if optimizer None, quit after single iteration
        schedule.delta_soc_all_trips()
        schedule.assign_vehicles(args.min_standing_time_depot)
        # write trips to csv in spiceEV format
        schedule.generate_scenario_json(args)

        # RUN SPICE EV
        spice_ev.simulate(args)
        if i == args.iterations:
            print(f"Rotations {schedule.get_negative_rotations(args)} have negative SoC.")
            break
        schedule.readjust_charging_type(args)
        i += 1

        # Quit if optimizer is not defined
        # (LATER) Run optimizer, continue from top or quit based on optimizer output
        # if optimizer.no_optimization() == 'converged':
        #    break

    # create report
    report.generate()