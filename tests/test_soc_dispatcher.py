import datetime
from argparse import Namespace
from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta
import sys
import pandas as pd
import pytest
import spice_ev.scenario as scenario
from spice_ev.util import set_options_from_config

from simba.simulate import pre_simulation
from simba.trip import Trip
from tests.conftest import example_root, file_root
from tests.helpers import generate_basic_schedule
from simba import consumption, rotation, schedule, trip, util


class TestSchedule:
    def basic_run(self):
        """Returns a schedule, scenario and args after running SimBA.
        :return: schedule, scenario, args
        """
        # set the system variables to imitate the console call with the config argument.
        # first element has to be set to something or error is thrown
        sys.argv = ["foo", "--config", str(example_root / "simba.cfg")]
        args = util.get_args()
        args.seed = 5
        args.attach_vehicle_soc = True
        sched, args = pre_simulation(args)

        # Copy an opportunity rotation twice, so dispatching can be tested
        assert sched.rotations["1"].charging_type == "oppb"
        sched.rotations["11"] = deepcopy(sched.rotations["1"])
        sched.rotations["12"] = deepcopy(sched.rotations["1"])
        sched.rotations["11"].id = "11"
        sched.rotations["12"].id = "12"

        # Mutate the first copy, so it ends later and has higher consumption
        sched.rotations["11"].trips[-1].arrival_time += timedelta(minutes=5)
        sched.rotations["11"].arrival_time += timedelta(minutes=5)

        sched.rotations["11"].trips[-1].distance += 10000
        # Mutate the second copy, so it starts later then "1" ends. This way a prev. vehicle can be used
        dt = sched.rotations["1"].arrival_time - \
             sched.rotations["12"].departure_time + \
             timedelta(minutes=20)
        for t in sched.rotations["12"].trips:
            t.arrival_time += dt
            t.departure_time += dt
        sched.rotations["12"].departure_time += dt
        sched.rotations["12"].arrival_time += dt

        # Copy a depot rotation, so a vehicle can be used again
        assert sched.rotations["2"].charging_type == "depb"

        sched.rotations["21"] = deepcopy(sched.rotations["2"])
        sched.rotations["21"].id = "21"
        dt = sched.rotations["2"].arrival_time - \
             sched.rotations["21"].departure_time + \
             timedelta(minutes=30)
        for t in sched.rotations["21"].trips:
            t.arrival_time += dt
            t.departure_time += dt
        sched.rotations["21"].departure_time += dt
        sched.rotations["21"].arrival_time += dt

        for v_type in Trip.consumption.vehicle_types.values():
            for charge_type in v_type.values():
                charge_type["mileage"] = 1

        # calculate consumption of all trips
        sched.calculate_consumption()
        sched.rotations["21"].consumption

        # Create soc dispatcher
        sched.init_soc_dispatcher(args)

        sched.assign_vehicles()
        scen = sched._run(args)

        for rot in sched.rotations.values():
            print(rot.id, rot.vehicle_id)

        return sched, scen, args

    @pytest.fixture
    def eflips_output(self):
        # eflipsoutput
        eflips_output = []

        @dataclass
        class eflips:
            rot_id: str
            v_id: str
            soc: float

        eflips_output.append(eflips(rot_id="4", v_id="AB_depb_1", soc=1))
        eflips_output.append(eflips(rot_id="3", v_id="AB_depb_2", soc=0.8))
        eflips_output.append(eflips(rot_id="2", v_id="AB_depb_3", soc=1))
        eflips_output.append(eflips(rot_id="21", v_id="AB_depb_3", soc=0.69))
        eflips_output.append(eflips(rot_id="1", v_id="AB_oppb_1", soc=1))
        eflips_output.append(eflips(rot_id="11", v_id="AB_oppb_2", soc=0.6))
        eflips_output.append(eflips(rot_id="12", v_id="AB_oppb_1", soc=0.945))
        return eflips_output

    def test_basic_dispatching(self, eflips_output):
        """Returns a schedule, scenario and args after running SimBA.
        :return: schedule, scenario, args
        """
        sched, scen, args = self.basic_run()
        pd.DataFrame(scen.vehicle_socs).plot()

        sched.assign_vehicles_for_django(eflips_output)
        for rotation in sched.rotations.values():
            print(rotation.vehicle_id)
        scen = sched._run(args)

        for rot in sched.rotations.values():
            print(rot.id, rot.vehicle_id)
        pd.DataFrame(scen.vehicle_socs).plot()

        return sched, scen, args

    def test_basic_missing_rotation(self, eflips_output):
        """Returns a schedule, scenario and args after running SimBA.
        :return: schedule, scenario, args
        """
        sched, scen, args = self.basic_run()
        # delete data for a single rotation but keep the rotation_id
        missing_rot_id = eflips_output[-1].rot_id
        del eflips_output[-1]

        # if data for a rotation is missing an error containing the rotation id should be raised
        with pytest.raises(KeyError, match=missing_rot_id):
            sched.assign_vehicles_for_django(eflips_output)
