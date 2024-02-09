from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta
import sys
import pandas as pd
import pytest

from simba.simulate import pre_simulation
from simba.trip import Trip
from tests.conftest import example_root
from simba import util


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
        # Mutate the second copy, so it starts later than "1" ends.
        # This way a prev. vehicle can be used.
        dt = sched.rotations["1"].arrival_time - sched.rotations["12"].departure_time + timedelta(
            minutes=20)
        for t in sched.rotations["12"].trips:
            t.arrival_time += dt
            t.departure_time += dt
        sched.rotations["12"].departure_time += dt
        sched.rotations["12"].arrival_time += dt

        # Copy a depot rotation, so a vehicle can be used again
        assert sched.rotations["2"].charging_type == "depb"

        sched.rotations["21"] = deepcopy(sched.rotations["2"])
        sched.rotations["21"].id = "21"
        dt = sched.rotations["2"].arrival_time - sched.rotations["21"].departure_time + timedelta(
            minutes=30)
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
        scen = sched.run(args)

        for rot in sched.rotations.values():
            print(rot.id, rot.vehicle_id)

        return sched, scen, args

    @pytest.fixture
    def eflips_output(self):
        # eflipsoutput
        eflips_output = []

        @dataclass
        class eflips:
            rotation_id: str
            vehicle_id: str
            soc_departure: float

        eflips_output.append(eflips(rotation_id="4", vehicle_id="AB_depb_1", soc_departure=1))
        eflips_output.append(eflips(rotation_id="3", vehicle_id="AB_depb_2", soc_departure=0.8))
        eflips_output.append(eflips(rotation_id="2", vehicle_id="AB_depb_3", soc_departure=1))
        eflips_output.append(eflips(rotation_id="21", vehicle_id="AB_depb_3", soc_departure=0.69))
        eflips_output.append(eflips(rotation_id="1", vehicle_id="AB_oppb_1", soc_departure=1))
        eflips_output.append(eflips(rotation_id="11", vehicle_id="AB_oppb_2", soc_departure=0.6))
        eflips_output.append(eflips(rotation_id="12", vehicle_id="AB_oppb_1", soc_departure=0.945))
        return eflips_output

    def test_basic_dispatching(self, eflips_output):
        """Returns a schedule, scenario and args after running SimBA.
        :param eflips_output: list of eflips data
        :return: schedule, scenario, args
        """
        sched, scen, args = self.basic_run()
        pd.DataFrame(scen.vehicle_socs).plot()

        sched.assign_vehicles_for_django(eflips_output)
        scen = sched.run(args)

        pd.DataFrame(scen.vehicle_socs).plot()

        return sched, scen, args

    def test_basic_missing_rotation(self, eflips_output):
        """Test if missing a rotation throws an error
        :param eflips_output: list of eflips data
        """
        sched, scen, args = self.basic_run()
        # delete data for a single rotation but keep the rotation_id
        missing_rot_id = eflips_output[-1].rotation_id
        del eflips_output[-1]

        # if data for a rotation is missing an error containing the rotation id should be raised
        with pytest.raises(KeyError, match=missing_rot_id):
            sched.assign_vehicles_for_django(eflips_output)