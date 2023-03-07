""" Module to generate meaningful output files and/or figures to describe simulation process
"""
import csv
import datetime
import warnings
import matplotlib.pyplot as plt
from src.report import aggregate_global_results, plot, generate_reports


def generate_gc_power_overview_timeseries(scenario, args):
    """Generate a csv timeseries with each grid connector's summed up charging station power

    :param scenario: Scenario for with to generate timeseries.
    :type scenario: spice_ev.Scenario
    :param args: Configuration arguments specified in config files contained in configs directory.
    :type args: argparse.Namespace
    """

    gc_list = list(scenario.constants.grid_connectors.keys())

    with open(args.output_directory / "gc_power_overview_timeseries.csv", "w", newline='') as f:
        csv_writer = csv.writer(f)
        csv_writer.writerow(["time"] + gc_list)
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
    """Generate a csv file with information regarding electrified stations.

    For each electrified station, the name, type, max. power, max. number of occupied
    charging stations, sum of charged energy and use factors of least used stations is saved.

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
                max_nr_cs = max(ts["CS in use"])
                sum_of_cs_energy = sum(ts["sum CS power"]) * args.interval/60

                # use factors: to which percentage of time are the three least used CS in use
                num_ts = scenario.n_intervals  # number of timesteps
                # three least used CS. Less if number of CS is lower.
                least_used_num = min(3, max_nr_cs)
                # count number of timesteps with this exact number of occupied CS
                count_nr_cs = [ts["CS in use"].count(max_nr_cs - i) for i in range(
                    least_used_num)]
                use_factors = [sum(count_nr_cs[:i + 1]) / num_ts for i in range(
                    least_used_num)]  # relative occupancy with at least this number of occupied CS
                use_factors = use_factors + [None] * (3 - least_used_num)  # fill up line with None

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


def bus_type_distribution_consumption_rotation(args, schedule):
    """Plots the distribution of bus types in consumption brackets as a stacked bar chart.

    :param args: Configuration arguments from cfg file. args.output_directory is used
    :type args: argparse.Namespace
    :param schedule: Driving schedule for the simulation. schedule.rotations are used
    :type schedule: eBus-Toolbox.Schedule
    """

    step = 50
    max_con = int(max([schedule.rotations[rot].consumption for rot in schedule.rotations]))
    if max_con % step < step / 2:
        max_con_up = ((max_con // step) * step)
    else:
        max_con_up = (max_con // step) * step + step
    labels = [f"{i - step} - {i}" for i in range(step, int(max_con), step) if i > 0]
    bins = {v_types: [0 for _ in range(int(max_con / step))] for v_types in schedule.vehicle_types}

    # fill bins with rotations
    for rot in schedule.rotations:
        for v_type in schedule.vehicle_types:
            if schedule.rotations[rot].vehicle_type == v_type:
                position = int(schedule.rotations[rot].consumption // step)
                if position >= max_con_up / step:
                    position -= 1
                bins[v_type][position] += 1
                break
    # plot
    fig, ax = plt.subplots()
    bar_bottom = [0 for _ in range(max_con_up//step)]
    for v_type in schedule.vehicle_types:
        ax.bar(labels, bins[v_type], width=0.9, label=v_type, bottom=bar_bottom)
        # something more efficient than for loop
        for i in range(max_con_up//step):
            bar_bottom[i] += bins[v_type][i]
    ax.set_xlabel('Energieverbrauch in kWh')
    ax.set_ylabel('Anzahl der Umläufe')
    ax.set_title('Verteilung der Bustypen über den Energieverbrauch und den Umläufen')
    ax.legend()
    fig.autofmt_xdate()
    ax.yaxis.grid(True)
    plt.savefig(args.output_directory / "distribution_bustypes_consumption_rotations")


def charge_type_proportion(args, schedule):
    """Plots the absolute number of rotations distributed by charging types on a bar chart.

    :param args: Configuration arguments from cfg file. args.output_directory is used
    :type args: argparse.Namespace
    :param schedule: Driving schedule for the simulation. schedule.rotations are used
    :type schedule: eBus-Toolbox.Schedule
    """
    # get plotting data
    charging_types = {'oppb': 0, 'depb': 0, 'rest': 0}
    for rot in schedule.rotations:
        if schedule.rotations[rot].charging_type == 'oppb':
            charging_types['oppb'] += 1
        elif schedule.rotations[rot].charging_type == 'depb':
            charging_types['depb'] += 1
        else:
            charging_types['rest'] += 1
    # plot
    fig, ax = plt.subplots()
    ax.bar(
        [k for k in charging_types.keys()],
        [v for v in charging_types.values()],
        color=['#6495ED', '#66CDAA', 'grey']
    )
    ax.set_xlabel("Ladetyp")
    ax.set_ylabel("Umläufe")
    ax.set_title("Verteilung von Gelegenheitslader, Depotlader und nicht elektrifizierbaren")
    ax.bar_label(ax.containers[0], [v for v in [v for v in charging_types.values()]])
    ax.yaxis.grid(True)
    plt.savefig(args.output_directory / "charge_type_proportion")


def gc_power_time_overview_example(args, schedule, scenario):

    gc_list = list(scenario.constants.grid_connectors.keys())
    for gc in gc_list:
        # data
        ts = getattr(scenario, f"{gc}_timeseries")
        time = ts["time"]
        total = ts["grid power [kW]"]
        feed_in = ts["feed-in [kW]"]
        ext_load = ts["ext.load [kW]"]
        cs = ts["sum CS power"]

        # plot
        plt.plot(time, total, label="total")
        plt.plot(time, feed_in, label="feed_in")
        plt.plot(time, ext_load, label="ext_load")
        plt.plot(time, cs, label="CS")
        plt.legend()
        plt.xticks(rotation=45)

        plt.savefig(args.output_directory / f"{gc}_power_time_overview")
        plt.clf()


def gc_power_time_overview(args, scenario):
    """Plots the different loads (total, feedin, external) of all grid connectors.

    :param args: Configuration arguments from cfg file. args.output_directory is used
    :type args: argparse.Namespace
    :param scenario: Provides the data for the grid connectors over time.
    :type scenario: spice_ev.Scenario
    """
    gc_list = list(scenario.constants.grid_connectors.keys())
    for gc in gc_list:
        ts = [
            scenario.start_time if i == 0 else
            scenario.start_time+scenario.interval*i for i in range(scenario.n_intervals)
        ]
        plt.plot(ts, scenario.totalLoad[gc], label="total")
        plt.plot(ts, scenario.feedInPower[gc], label="feed_in")
        plt.plot(ts, [sum(v.values()) for v in scenario.extLoads[gc]], label="ext_load")
        plt.legend()
        plt.xticks(rotation=30)

        gc = gc.replace("/", "").replace(".", "")
        plt.savefig(args.output_directory / f"{gc}_power_time_overview")
        plt.close()


def generate(schedule, scenario, args, extended_plots=False):
    """Generates all output files/ plots and saves them in the output directory.

    :param schedule: Driving schedule for the simulation.
    :type schedule: eBus-Toolbox.Schedule
    :param scenario: Scenario for with to generate timeseries.
    :type scenario: spice_ev.Scenario
    :param args: Configuration arguments specified in config files contained in configs directory.
    :type args: argparse.Namespace
    :param extended_plots: Generates more plots.
    :type extended_plots: bool
    """

    # generate if needed extended output plots
    if extended_plots:
        bus_type_distribution_consumption_rotation(args, schedule)
        charge_type_proportion(args, schedule)
        gc_power_time_overview(args, scenario)

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

    print("Plots and output files saved in", args.output_directory)
