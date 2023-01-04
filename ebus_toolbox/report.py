""" Module to generate meaningful output files and/or figures to describe simulation process
"""
import csv
import datetime
import warnings
import matplotlib.pyplot as plt
from src.report import aggregate_global_results, plot, generate_reports


def generate_gc_power_overview_timeseries(scenario, args):
    """Generates a csv file from each grid connectors summed up
    charging station power in the specified simulation time.

    :param scenario: Scenario for with to generate timeseries.
    :type scenario: spice_ev.Scenario
    :param args: Configuration arguments specified in config files contained in configs directory.
    :type args: argparse.Namespace
    """

    gc_list = list(scenario.constants.grid_connectors.keys())

    with open(args.output_directory / "gc_power_overview_timeseries.csv", "w", newline='') as f:
        csv_writer = csv.writer(f)
        csv_writer.writerow(["time", ] + gc_list)
        stations = []
        time_col = getattr(scenario, f"{gc_list[0]}_timeseries")["time"]
        for i in range(len(time_col)):
            time_col[i] = time_col[i].isoformat()
        stations.append(time_col)
        for gc in gc_list:
            stations.append([-x for x in getattr(scenario, f"{gc}_timeseries")["grid power [kW]"]])
        gc_power_overview = list(map(list, zip(*stations)))
        csv_writer.writerows(gc_power_overview)


def generate_gc_overview(schedule, scenario, args):
    """Generates a csv file where each line an electrified station's maximum power
    and maximum number of charging stations is shown.

    :param schedule: Driving schedule for the simulation.
    :type schedule: eBus-Toolbox.Schedule
    :param scenario: Scenario for with to generate timeseries.
    :type scenario: spice_ev.Scenario
    :param args: Configuration arguments specified in config files contained in configs directory.
    :type args: argparse.Namespace
    """

    all_gc_list = list(schedule.stations.keys())
    used_gc_list = list(scenario.constants.grid_connectors.keys())
    stations = getattr(schedule, "stations")

    with open(args.output_directory / "gc_overview.csv", "w", newline='') as f:
        csv_writer = csv.writer(f)
        csv_writer.writerow(["station_name",
                             "station_type",
                             "maximum_power",
                             "maximum Nr charging stations",
                             "sum of CS energy",
                             "use factor least CS",
                             "use factor 2nd least CS",
                             "use factor 3rd least CS"])
        for gc in all_gc_list:
            if gc in used_gc_list:
                ts = getattr(scenario, f"{gc}_timeseries")
                max_gc_power = -min(ts["grid power [kW]"])
                max_nr_cs = max(ts["# occupied CS"])
                sum_of_cs_energy = sum(ts["sum CS power"]) * args.interval/60

                # use factors: to which percentage of time are the three least used CS in use
                least_used_cs = [max_nr_cs, max_nr_cs-1, max_nr_cs-2]
                use_factors = [None, None, None]
                for i in range(3):
                    if least_used_cs[i] >= 1:
                        use_factors[i] = sum([ts["# occupied CS"].count(least_used_cs[j]) /
                                              len(ts["# occupied CS"]) for j in range(i+1)])
            else:
                max_gc_power = 0
                max_nr_cs = 0
                sum_of_cs_energy = 0
                use_factors = [None, None, None]
            station_type = stations[gc]["type"]
            csv_writer.writerow([gc,
                                 station_type,
                                 max_gc_power,
                                 max_nr_cs,
                                 sum_of_cs_energy,
                                 *use_factors])


def generate(schedule, scenario, args):
    """Generates all output files/ plots and saves them in the output directory.

    :param schedule: Driving schedule for the simulation.
    :type schedule: eBus-Toolbox.Schedule
    :param scenario: Scenario for with to generate timeseries.
    :type scenario: spice_ev.Scenario
    :param args: Configuration arguments specified in config files contained in configs directory.
    :type args: argparse.Namespace
    """

    # generate simulation_timeseries.csv, simulation.json and vehicle_socs.csv in spiceEV
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        generate_reports(scenario, vars(args).copy())

    # generate gc power overview
    generate_gc_power_overview_timeseries(scenario, args)

    # generate gc overview
    generate_gc_overview(schedule, scenario, args)

    # save plots as png and pdf
    aggregate_global_results(scenario)
    with plt.ion():     # make plotting temporarily interactive, so plt.show does not block
        plot(scenario)
        plt.gcf().set_size_inches(10, 10)
        plt.savefig(args.output_directory / "run_overview.png")
        plt.savefig(args.output_directory / "run_overview.pdf")
        if not args.show_plots:
            plt.close()

    # calculate SOCs for each rotation
    rotation_infos = []

    negative_rotations = schedule.get_negative_rotations(scenario)

    interval = datetime.timedelta(minutes=args.interval)
    sim_start_time = \
        schedule.get_departure_of_first_trip() - datetime.timedelta(minutes=args.signal_time_dif)

    incomplete_rotations = []
    rotation_socs = {}
    for id, rotation in schedule.rotations.items():
        # get SOC timeseries for this rotation
        vehicle_id = rotation.vehicle_id

        # get soc timeseries for current rotation
        vehicle_soc = scenario.vehicle_socs[vehicle_id]
        start_idx = (rotation.departure_time - sim_start_time) // interval
        end_idx = start_idx + ((rotation.arrival_time - rotation.departure_time) // interval)
        if end_idx > scenario.n_intervals:
            # SpiceEV stopped before rotation was fully simulated
            incomplete_rotations.append(id)
            continue
        rotation_soc_ts = vehicle_soc[start_idx:end_idx]

        # bus does not return before simulation end
        # replace trailing None values with last numeric value
        for i, soc in enumerate(reversed(rotation_soc_ts)):
            if soc is not None:
                break
        last_known_idx = len(rotation_soc_ts) - 1 - i
        rotation_soc_ts[last_known_idx + 1:] = i * [rotation_soc_ts[last_known_idx]]

        rotation_info = {
            "rotation_id": id,
            "start_time": rotation.departure_time.isoformat(),
            "end_time": rotation.arrival_time.isoformat(),
            "vehicle_type": rotation.vehicle_type,
            "vehicle_id": rotation.vehicle_id,
            "depot_name": rotation.departure_name,
            "lines": ':'.join(rotation.lines),
            "total_consumption_[kWh]": rotation.consumption,
            "distance": rotation.distance,
            "charging_type": rotation.charging_type,
            "SOC_at_arrival": rotation_soc_ts[-1],
            "Minimum_SOC": min(rotation_soc_ts),
            "Negative_SOC": 1 if id in negative_rotations else 0
        }
        rotation_infos.append(rotation_info)

        # save SOCs for each rotation
        rotation_socs[id] = [None] * scenario.n_intervals
        rotation_socs[id][start_idx:end_idx] = rotation_soc_ts

    if incomplete_rotations:
        warnings.warn("SpiceEV stopped before simulation of the these rotations were completed:\n"
                      f"{', '.join(incomplete_rotations)}\n"
                      "Omit parameter <days> to simulate entire schedule.",
                      stacklevel=100)

    with open(args.output_directory / "rotation_socs.csv", "w+", newline='') as f:
        csv_writer = csv.writer(f)
        csv_writer.writerow(("time",) + tuple(rotation_socs.keys()))
        for i, row in enumerate(zip(*rotation_socs.values())):
            t = sim_start_time + i * scenario.interval
            csv_writer.writerow((t,) + row)

    with open(args.output_directory / "rotation_summary.csv", "w+", newline='') as f:
        csv_writer = csv.DictWriter(f, list(rotation_infos[0].keys()))
        csv_writer.writeheader()
        csv_writer.writerows(rotation_infos)

    # summary of used vehicle types and all costs
    if args.cost_calculation:
        with open(args.output_directory / "summary_vehicles_costs.csv", "w", newline='') as f:
            csv_writer = csv.writer(f)
            csv_writer.writerow(["parameter", "value", "unit"])
            for key, value in schedule.vehicle_type_counts.items():
                if value > 0:
                    csv_writer.writerow([key, value, "vehicles"])
            for key, value in scenario.costs.items():
                if "annual" in key:
                    csv_writer.writerow([key, round(value, 2), "€/year"])
                else:
                    csv_writer.writerow([key, round(value, 2), "€"])

    print("Plots and output files saved in " + str(args.output_directory))
