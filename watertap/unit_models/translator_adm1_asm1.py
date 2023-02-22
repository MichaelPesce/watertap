#################################################################################
# The Institute for the Design of Advanced Energy Systems Integrated Platform
# Framework (IDAES IP) was produced under the DOE Institute for the
# Design of Advanced Energy Systems (IDAES), and is copyright (c) 2018-2021
# by the software owners: The Regents of the University of California, through
# Lawrence Berkeley National Laboratory,  National Technology & Engineering
# Solutions of Sandia, LLC, Carnegie Mellon University, West Virginia University
# Research Corporation, et al.  All rights reserved.
#
# Please see the files COPYRIGHT.md and LICENSE.md for full copyright and
# license information.
#################################################################################
"""
Modified translator block.

This is copied from the Generic template for a translator block.

Assumptions:
     * Steady-state only

Model formulated from:

Copp J. and Jeppsson, U., Rosen, C., 2006.
Towards an ASM1 - ADM1 State Variable Interface for Plant-Wide Wastewater Treatment Modeling.
 Proceedings of the Water Environment Federation, 2003, pp 498-510.
"""

# Import Pyomo libraries
from pyomo.common.config import ConfigBlock, ConfigValue, In, Bool

# Import IDAES cores
from idaes.core import declare_process_block_class, UnitModelBlockData
from idaes.core.util.config import (
    is_physical_parameter_block,
    is_reaction_parameter_block,
)
from idaes.core.util.model_statistics import degrees_of_freedom
from idaes.core.util.exceptions import ConfigurationError
from idaes.core.solvers import get_solver
import idaes.logger as idaeslog

from pyomo.environ import (
    Reference,
    Var,
    value,
    Constraint,
    Param,
    units as pyunits,
    check_optimal_termination,
    exp,
    Set,
    PositiveReals,
)

__author__ = "Alejandro Garciadiego, Andrew Lee"


# Set up logger
_log = idaeslog.getLogger(__name__)


@declare_process_block_class("Translator_ADM1_ASM1")
class TranslatorData(UnitModelBlockData):
    """
    Standard Translator Block Class
    """

    CONFIG = ConfigBlock()
    CONFIG.declare(
        "dynamic",
        ConfigValue(
            domain=In([False]),
            default=False,
            description="Dynamic model flag - must be False",
            doc="""Translator blocks are always steady-state.""",
        ),
    )
    CONFIG.declare(
        "has_holdup",
        ConfigValue(
            default=False,
            domain=In([False]),
            description="Holdup construction flag - must be False",
            doc="""Translator blocks do not contain holdup.""",
        ),
    )
    CONFIG.declare(
        "has_phase_equilibrium",
        ConfigValue(
            default=False,
            domain=Bool,
            description="Phase equilibrium construction flag",
            doc="""Indicates whether terms for phase equilibrium should be
    constructed,
    **default** = False.
    **Valid values:** {
    **True** - include phase equilibrium terms
    **False** - exclude phase equilibrium terms.}""",
        ),
    )
    CONFIG.declare(
        "outlet_state_defined",
        ConfigValue(
            default=True,
            domain=Bool,
            description="Indicated whether outlet state will be fully defined",
            doc="""Indicates whether unit model will fully define outlet state.
If False, the outlet property package will enforce constraints such as sum
of mole fractions and phase equilibrium.
**default** - True.
**Valid values:** {
**True** - outlet state will be fully defined,
**False** - outlet property package should enforce sumation and equilibrium
constraints.}""",
        ),
    )
    CONFIG.declare(
        "inlet_property_package",
        ConfigValue(
            default=None,
            domain=is_physical_parameter_block,
            description="Property package to use for incoming stream",
            doc="""Property parameter object used to define property
calculations for the incoming stream,
**default** - None.
**Valid values:** {
**PhysicalParameterObject** - a PhysicalParameterBlock object.}""",
        ),
    )
    CONFIG.declare(
        "inlet_property_package_args",
        ConfigBlock(
            implicit=True,
            description="Arguments to use for constructing property package "
            "of the incoming stream",
            doc="""A ConfigBlock with arguments to be passed to the property
block associated with the incoming stream,
**default** - None.
**Valid values:** {
see property package for documentation.}""",
        ),
    )
    CONFIG.declare(
        "outlet_property_package",
        ConfigValue(
            default=None,
            domain=is_physical_parameter_block,
            description="Property package to use for outgoing stream",
            doc="""Property parameter object used to define property
calculations for the outgoing stream,
**default** - None.
**Valid values:** {
**PhysicalParameterObject** - a PhysicalParameterBlock object.}""",
        ),
    )
    CONFIG.declare(
        "outlet_property_package_args",
        ConfigBlock(
            implicit=True,
            description="Arguments to use for constructing property package "
            "of the outgoing stream",
            doc="""A ConfigBlock with arguments to be passed to the property
block associated with the outgoing stream,
**default** - None.
**Valid values:** {
see property package for documentation.}""",
        ),
    )

    def build(self):
        """
        Begin building model.
        Args:
            None
        Returns:
            None
        """
        # Call UnitModel.build to setup dynamics
        super(TranslatorData, self).build()

        self.N_I = Param(
            initialize=0.06
            / 14,  # change from 0.002 to 0.06/14 based on Rosen & Jeppsson, 2006
            units=pyunits.kmol * pyunits.kg**-1,
            mutable=True,
            doc="Nitrogen content of inerts [kmole N/kg COD]",
        )
        self.N_aa = Param(
            initialize=0.007,
            units=pyunits.kmol * pyunits.kg**-1,
            mutable=True,
            doc="Nitrogen in amino acids and proteins [kmole N/kg COD]",
        )
        self.N_bac = Param(
            initialize=0.08 / 14,
            units=pyunits.kmol * pyunits.kg**-1,
            mutable=True,
            doc="Nitrogen content in bacteria [kmole N/kg COD]",
        )

        self.i_ec = Param(
            initialize=0.06,
            units=pyunits.dimensionless,
            mutable=True,
            doc="Nitrogen inert content",
        )

        # Add State Blocks
        self.properties_in = self.config.inlet_property_package.build_state_block(
            self.flowsheet().time,
            doc="Material properties in incoming stream",
            defined_state=True,
            has_phase_equilibrium=False,
            **self.config.inlet_property_package_args
        )

        self.properties_out = self.config.outlet_property_package.build_state_block(
            self.flowsheet().time,
            doc="Material properties in outgoing stream",
            defined_state=self.config.outlet_state_defined,
            has_phase_equilibrium=False,
            **self.config.outlet_property_package_args
        )

        # Add ports
        self.add_port(name="inlet", block=self.properties_in, doc="Inlet Port")
        self.add_port(name="outlet", block=self.properties_out, doc="Outlet Port")

        @self.Constraint(
            self.flowsheet().time,
            doc="Equality volumetric flow equation",
        )
        def eq_flow_vol_rule(blk, t):
            return blk.properties_out[t].flow_vol == blk.properties_in[t].flow_vol

        @self.Constraint(
            self.flowsheet().time,
            doc="Equality temperature equation",
        )
        def eq_temperature_rule(blk, t):
            return blk.properties_out[t].temperature == blk.properties_in[t].temperature

        @self.Constraint(
            self.flowsheet().time,
            doc="Equality pressure equation",
        )
        def eq_pressure_rule(blk, t):
            return blk.properties_out[t].pressure == blk.properties_in[t].pressure

        @self.Constraint(
            self.flowsheet().time,
            doc="Equality S_I equation",
        )
        def eq_SI_conc(blk, t):
            return (
                blk.properties_out[t].conc_mass_comp["S_I"]
                == blk.properties_in[t].conc_mass_comp["S_I"]
            )

        @self.Constraint(
            self.flowsheet().time,
            doc="Equality X_I equation",
        )
        def eq_XI_conc(blk, t):
            return (
                blk.properties_out[t].conc_mass_comp["X_I"]
                == blk.properties_in[t].conc_mass_comp["X_I"]
            )

        self.readily_biodegradable = Set(
            initialize=["S_su", "S_aa", "S_fa", "S_va", "S_bu", "S_pro", "S_ac"]
        )

        self.slowly_biodegradable = Set(
            initialize=[
                "X_c",
                "X_ch",
                "X_pr",
                "X_li",
                "X_su",
                "X_aa",
                "X_fa",
                "X_c4",
                "X_pro",
                "X_ac",
                "X_h2",
            ]
        )

        @self.Constraint(
            self.flowsheet().time,
            doc="Equality S_S equation",
        )
        def eq_SS_conc(blk, t):
            return blk.properties_out[t].conc_mass_comp["S_S"] == sum(
                blk.properties_in[t].conc_mass_comp[i]
                for i in blk.readily_biodegradable
            )

        @self.Constraint(
            self.flowsheet().time,
            doc="Equality X_S equation",
        )
        def eq_XS_conc(blk, t):
            return blk.properties_out[t].conc_mass_comp["X_S"] == sum(
                blk.properties_in[t].conc_mass_comp[i] for i in blk.slowly_biodegradable
            )

        @self.Constraint(
            self.flowsheet().time,
            doc="Equality S_NH equation",
        )
        def eq_Snh_conc(blk, t):
            return (
                blk.properties_out[t].conc_mass_comp["S_NH"]
                == blk.properties_in[t].conc_mass_comp["S_IN"]
            )

        @self.Constraint(
            self.flowsheet().time,
            doc="Equality S_ND equation",
        )
        def eq_Snd_conc(blk, t):
            return blk.properties_out[t].conc_mass_comp["S_ND"] == (
                blk.properties_in[t].conc_mass_comp["S_I"] * blk.N_I
            ) + (blk.properties_in[t].conc_mass_comp["S_I"] * blk.N_aa)

        @self.Constraint(
            self.flowsheet().time,
            doc="Equality Xnd equation",
        )
        def eq_Xnd_conc(blk, t):
            return blk.properties_out[t].conc_mass_comp["X_ND"] == (
                (
                    blk.N_bac
                    * (
                        blk.properties_in[t].conc_mass_comp["X_su"]
                        + blk.properties_in[t].conc_mass_comp["X_aa"]
                        + blk.properties_in[t].conc_mass_comp["X_fa"]
                        + blk.properties_in[t].conc_mass_comp["X_c4"]
                        + blk.properties_in[t].conc_mass_comp["X_pro"]
                        + blk.properties_in[t].conc_mass_comp["X_ac"]
                        + blk.properties_in[t].conc_mass_comp["X_h2"]
                    )
                )
                + (blk.properties_in[t].conc_mass_comp["X_I"] * blk.N_I)
                + (blk.properties_in[t].conc_mass_comp["X_c"] * blk.N_I)
                + (blk.properties_in[t].conc_mass_comp["X_pr"] * blk.N_aa)
                - (blk.properties_in[t].conc_mass_comp["X_I"] * blk.N_I * blk.i_ec)
            )

        @self.Constraint(
            self.flowsheet().time,
            doc="Equality alkalinity equation",
        )
        def return_Salk(blk, t):
            return (
                blk.properties_out[t].alkalinity
                == blk.properties_in[t].conc_mass_comp["S_IC"]
            )

        self.zero_flow_components = Set(
            initialize=["X_BH", "X_BA", "X_P", "S_O", "S_NO"]
        )

        @self.Constraint(
            self.flowsheet().time,
            self.zero_flow_components,
            doc="Components with no flow equation",
        )
        def return_zero_flow_comp(blk, t, i):
            return blk.properties_out[t].conc_mass_comp[i] == 1e-6

    def initialize_build(
        blk,
        state_args_in=None,
        state_args_out=None,
        outlvl=idaeslog.NOTSET,
        solver=None,
        optarg=None,
    ):
        """
        This method calls the initialization method of the state blocks.
        Keyword Arguments:
            state_args_in : a dict of arguments to be passed to the inlet
                            property package (to provide an initial state for
                            initialization (see documentation of the specific
                            property package) (default = None).
            state_args_out : a dict of arguments to be passed to the outlet
                             property package (to provide an initial state for
                             initialization (see documentation of the specific
                             property package) (default = None).
            outlvl : sets output level of initialization routine
            optarg : solver options dictionary object (default=None, use
                     default solver options)
            solver : str indicating which solver to use during
                     initialization (default = None, use default solver)
        Returns:
            None
        """
        init_log = idaeslog.getInitLogger(blk.name, outlvl, tag="unit")

        # Create solver
        opt = get_solver(solver, optarg)

        # ---------------------------------------------------------------------
        # Initialize state block
        flags = blk.properties_in.initialize(
            outlvl=outlvl,
            optarg=optarg,
            solver=solver,
            state_args=state_args_in,
            hold_state=True,
        )

        blk.properties_out.initialize(
            outlvl=outlvl,
            optarg=optarg,
            solver=solver,
            state_args=state_args_out,
        )

        if degrees_of_freedom(blk) == 0:
            with idaeslog.solver_log(init_log, idaeslog.DEBUG) as slc:
                res = opt.solve(blk, tee=slc.tee)

            init_log.info("Initialization Complete {}.".format(idaeslog.condition(res)))
        else:
            init_log.warning(
                "Initialization incomplete. Degrees of freedom "
                "were not zero. Please provide sufficient number "
                "of constraints linking the state variables "
                "between the two state blocks."
            )

        blk.properties_in.release_state(flags=flags, outlvl=outlvl)
