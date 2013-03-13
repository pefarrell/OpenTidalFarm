import finite_elements
import numpy
from dirichlet_bc import DirichletBCSet
from turbines import TurbineCache
from dolfin import * 
from math import exp, sqrt, pi
from initial_conditions import *
from domains import *
from helpers import info, info_green, info_red, info_blue

class Parameters(dict):
    '''Parameter dictionary. This subclasses dict so defaults can be set.'''
    def __init__(self, dict={}):
        # Apply dict after defaults so as to overwrite the defaults
        for key,val in dict.iteritems():
            self[key]=val

        self.required={
            'verbose' : 'output verbosity',
            'dt' : 'timestep',
            'theta' : 'the implicitness for the time discretisation',
            'start_time' : 'start time',
            'current_time' : 'current time',
            'finish_time' : 'finish time',
            'steady_state' : 'steady state simulation',
            'functional_final_time_only' : 'if the functional should be evaluated at the final time only (used if the time stepping is used to converge to a steady state)',
            'dump_period' : 'dump period in timesteps; use 0 to deactivate disk outputs',
            'bctype'  : 'type of boundary condition to be applied',
            'strong_bc'  : 'list of strong dirichlet boundary conditions to be applied',
            'free_slip_on_sides' : 'apply free slip boundary conditions on the sides (id=3)',
            'initial_condition'  : 'initial condition function',
            'include_advection': 'advection term on',
            'include_diffusion': 'diffusion term on',
            'diffusion_coef': 'diffusion coefficient',
            'depth' : 'water depth at rest',
            'g' : 'graviation',
            'k' : 'wave length paramter. If you want a wave lenght of l, then set k to 2*pi/l.',
            'eta0' : 'amplitude of free surface elevation',
            'quadratic_friction' : 'quadratic friction',
            'friction' : 'friction term on',
            'turbine_pos' : 'list of turbine positions',
            'turbine_x' : 'turbine extension in the x direction',
            'turbine_y' : 'turbine extension in the y direction',
            'turbine_friction' : 'turbine friction', 
            'rho' : 'the density of the fluid', 
            'controls' : 'the control variables',
            'newton_solver': 'newton solver instead of a picard iteration',
            'linear_solver' : 'default linear solver',
            'preconditioner' : 'default preconditioner',
            'picard_relative_tolerance': 'relative tolerance for the picard iteration',
            'picard_iterations': 'maximum number of picard iterations',
            'run_benchmark': 'benchmark to compare different solver/preconditioner combinations', 
            'solver_exclude': 'solvers/preconditioners to be excluded from the benchmark',
            'automatic_scaling': 'activates the initial automatic scaling of the functional',
            'automatic_scaling_multiplier': 'defines the multiplier that determines the initial gradient length (= multiplier * turbine size)',
            'print_individual_turbine_power': 'print out the power output of each individual turbine',
            'save_checkpoints': 'automatically store checkpoints after each optimisation iteration'
            }

    def check(self):
        # First check that no parameters are missing
        for key, error in self.required.iteritems():
            if not self.has_key(key):
                raise KeyError, 'Missing parameter: ' + key + '. ' + 'This is used to set the ' + error + '.'
        # Then check that no parameter is too much (as this is likely to be a mistake!)
        diff = set(self.keys()) - set(self.required.keys())
        if len(diff) > 0:
            raise KeyError, 'Configuration has too many parameters: ' + str(diff)

class DefaultConfiguration(object):
  def __init__(self, nx=20, ny=3, basin_x = 3000, basin_y = 1000, finite_element = finite_elements.p2p1):

    # Initialize function space and the domain
    self.finite_element = finite_element
    self.set_domain( RectangularDomain(basin_x, basin_y, nx, ny), warning = False )

    params = Parameters({
        'verbose'  : 1,
        'theta' : 0.6,
        'steady_state' : False,
        'functional_final_time_only' : False,
        'initial_condition' : SinusoidalInitialCondition, 
        'bctype'  : 'flather',
        'strong_bc' : None,
        'free_slip_on_sides' : False,
        'include_advection': False,
        'include_diffusion': False,
        'diffusion_coef': 0.0,
        'depth' : 50.0,
        'g' : 9.81,
        'dump_period' : 1,
        'eta0' : 2, 
        'quadratic_friction' : False, 
        'friction' : 0.0, 
        'turbine_pos' : [],
        'turbine_x' : 20., 
        'turbine_y' : 5., 
        'turbine_friction' : [],
        'rho' : 1000., # Use the density of water: 1000kg/m^3
        'controls' : ['turbine_pos', 'turbine_friction'],
        'newton_solver': False, 
        'linear_solver' : 'mumps',
        'preconditioner' : 'default',
        'picard_relative_tolerance': 1e-5, 
        'picard_iterations': 3, 
        'run_benchmark': False, 
        'solver_exclude': ['cg'],
        'start_time': 0.,
        'current_time': 0.,
        'finish_time': 100.,
        'automatic_scaling': False,
        'automatic_scaling_multiplier': 5,
   		'print_individual_turbine_power': False,
   		'save_checkpoints': False
        })

    params['dt'] = params['finish_time']/4000.

    # Print log messages only from the root process in parallel
    # (See http://fenicsproject.org/documentation/dolfin/dev/python/demo/pde/navier-stokes/python/documentation.html)
    parameters['std_out_all_processes'] = False

    params['k'] = pi/self.domain.basin_x

    # Store the result as class variables
    self.params = params

    # Create a chaching object for the interpolated turbine friction fields (as their computation is very expensive)
    self.turbine_cache = TurbineCache()

  def set_domain(self, domain, warning = True):
      if warning:
           info_red("If you are overwriting the domain, make sure that you reapply the boundary conditions as well")
      self.domain = domain
      self.function_space = self.finite_element(self.domain.mesh)
      self.turbine_function_space = FunctionSpace(self.domain.mesh, 'CG', 2) 

  def set_turbine_pos(self, positions, friction = 1.0):
      ''' Sets the turbine position and a equal friction parameter. '''
      self.params['turbine_pos'] = positions
      self.params['turbine_friction'] = friction * numpy.ones(len(positions))

  def info(self):
    hmin = MPI.min(self.domain.mesh.hmin())
    hmax = MPI.max(self.domain.mesh.hmax())
    if MPI.process_number() == 0:
        s = "\n=== Physical parameters ===\n"
        if isinstance(self.params["depth"],float):
          s += "Water depth: %f m\n" % self.params["depth"]
        s += "Gravity constant: %f m/s^2\n" % self.params["g"]
        s += "Viscosity constant: %f m^2/s\n" % self.params["diffusion_coef"]
        s += "Water density: %f kg/m^3\n" % self.params["rho"]
        s += "Bottom friction: %s\n" % self.params["friction"]
        s += "Advection term: %s\n" % self.params["include_advection"]
        s += "Diffusion term: %s\n" % self.params["include_diffusion"]
        s += "Steady state: %s\n" % self.params["steady_state"]
        s += "\n=== Turbine settings ===\n"
        s += "Number of turbines: %i\n" % len(self.params["turbine_pos"])
        s += "Turbines dimensions: %f x %f\n" % (self.params["turbine_x"], self.params["turbine_y"])
        s += "Control parameters: %s\n" % ', '.join(self.params["controls"])
        if len(self.params["turbine_friction"]) > 0:
          s += "Turbines frictions: %f - %f\n" % (min(self.params["turbine_friction"]), max(self.params["turbine_friction"]))
        s += "\n=== Discretisation settings ===\n"
        if not self.params["steady_state"]:
            s += "Theta: %f\n" % self.params["theta"]
            s += "Start time: %f s\n" % self.params["start_time"]
            s += "Finish time: %f s\n" % self.params["finish_time"]
        s += "Number of mesh elements: %i\n" % self.domain.mesh.num_cells() 
        s += "Mesh element size: %f - %f\n" % (hmin, hmax)
        s += "\n=== Simulation settings ===\n"
        s += "Automatic checkpoint generation: %s\n" % self.params["save_checkpoints"] 
        print(s)

class BasePaperConfiguration(DefaultConfiguration):
  def __init__(self, nx = 20, ny = 3, basin_x = None, basin_y = None, finite_element = finite_elements.p2p1):
    # If no mesh file is given, we compute the domain size from the number of elements(nx and ny) with a 2m element size
    if not basin_x:
      basin_x = float(nx * 2) # Use a 2m element size by default
    if not basin_y:
      basin_y = float(ny * 2)

    super(BasePaperConfiguration, self).__init__(nx, ny, basin_x, basin_y, finite_element)

    # Model settings
    self.params['include_advection'] = True
    self.params['include_diffusion'] = True
    self.params['diffusion_coef'] = 3.0
    self.params['quadratic_friction'] = True
    self.params['newton_solver'] = True 
    self.params['friction'] = 0.0025

    # Turbine settings
    self.params['turbine_pos'] = []
    self.params['turbine_friction'] = []
    self.params['turbine_x'] = 20. 
    self.params['turbine_y'] = 20. 
    self.params['controls'] = ['turbine_pos']

    # Timing settings
    self.period = 1.24*60*60
    self.params['k'] =  None
    self.params['theta'] = 1.0
    self.params['start_time'] = 1./4*self.period
    self.params['dt'] = self.period/50
    self.params['finish_time'] = 3./4*self.period
    info('Wave period (in h): %f' % (self.period/60/60) )
    info('Approximate CFL number (assuming a velocity of 2): ' + str(2*self.params['dt']/self.domain.mesh.hmin()))

    # Finally set some optimistion flags 
    dolfin.parameters['form_compiler']['cpp_optimize'] = True
    dolfin.parameters['form_compiler']['cpp_optimize_flags'] = '-O3 -ffast-math -march=native'
    dolfin.parameters['form_compiler']['optimize'] = True

  def set_turbine_pos(self, position, friction = 0.25):
      ''' Sets the turbine position and a equal friction parameter. '''
      super(BasePaperConfiguration, self).set_turbine_pos(position, friction)

class PaperConfiguration(BasePaperConfiguration):
  def __init__(self, nx = 20, ny = 3, basin_x = None, basin_y = None, finite_element = finite_elements.p2p1):
    super(PaperConfiguration, self).__init__(nx, ny, basin_x, basin_y, finite_element)

    # Without the 1e-10, the adjoint model hangs! Why? No idea!
    self.params['eta0'] = (2.0+1e-10)/sqrt(self.params["g"]/self.params["depth"]) # This will give a inflow velocity of 2m/s
    self.params['k'] = 2*pi/(self.period*sqrt(self.params['g']*self.params['depth']))

    # Configure the boundary conditions
    self.params['bctype'] = 'strong_dirichlet'
    bc = DirichletBCSet(self)
    expression = Expression(("eta0*sqrt(g/depth)*cos(k*x[0]-sqrt(g*depth)*k*t)", "0"), eta0 = self.params["eta0"], g = self.params["g"], depth = self.params["depth"], t = self.params["current_time"], k = self.params["k"])
    bc.add_analytic_u(1, expression)
    bc.add_analytic_u(2, expression)
    bc.add_noslip_u(3)
    self.params['strong_bc'] = bc

class ConstantInflowPeriodicSidesPaperConfiguration(BasePaperConfiguration):
    def __init__(self, nx = 20, ny = 3, basin_x = None, basin_y = None, finite_element = finite_elements.p2p1):
        super(ConstantInflowPeriodicSidesPaperConfiguration, self).__init__(nx, ny, basin_x, basin_y, finite_element)
        self.set_site_dimensions(0, self.domain.basin_x, 0, self.domain.basin_y)

        # Without the 1e-10, the adjoint model hangs! Why? No idea!
        self.params['eta0'] = (2.0+1e-10)/sqrt(self.params["g"]/self.params["depth"]) # This will give a inflow velocity of 2m/s
        self.params['k'] = 2*pi/(self.period*sqrt(self.params['g']*self.params['depth']))

        self.params["initial_condition"] = ConstantFlowInitialCondition 
        self.params["newton_solver"] = False
        self.params["picard_iterations"] = 2
        self.params['theta'] = 1.0
        self.params['functional_final_time_only'] = True
        self.params['automatic_scaling'] = True

        self.params['bctype'] = 'strong_dirichlet'
        bc = DirichletBCSet(self)
        bc.add_constant_flow(1, 2.0+1e-10)
        bc.add_noslip_u(3)
        self.params['strong_bc'] = bc

        self.params['start_time'] = 0.0
        self.params['dt'] = self.period
        self.params['finish_time'] = self.params['start_time'] + self.params['dt'] 

    def set_site_dimensions(self, site_x_start, site_x_end, site_y_start, site_y_end):
        if not site_x_start < site_x_end or not site_y_start < site_y_end:
            raise ValueError, "Site must have a positive area"
        self.domain.site_x_start = site_x_start
        self.domain.site_y_start = site_y_start
        self.domain.site_x_end = site_x_end
        self.domain.site_y_end = site_y_end

    def set_turbine_pos(self, position, friction = 1.):
        ''' Sets the turbine position and a equal friction parameter. '''
        super(BasePaperConfiguration, self).set_turbine_pos(position, friction)

class ScenarioConfiguration(BasePaperConfiguration):
    def __init__(self, mesh_file, inflow_direction, finite_element = finite_elements.p2p1, turbine_friction = 21.):
        super(ScenarioConfiguration, self).__init__(nx = 100, ny = 33, basin_x = None, basin_y = None, finite_element = finite_element)
        self.set_domain( GMeshDomain(mesh_file), warning = False)
        self.params['k'] = None # let's hope this isn't used anymore

        self.params["initial_condition"] = ConstantFlowInitialCondition 
        self.params["newton_solver"] = False
        self.params["picard_iterations"] = 2
        self.params['theta'] = 1.0
        self.params['functional_final_time_only'] = True
        self.params['automatic_scaling'] = True

        self.params['start_time'] = 0.0
        self.params['dt'] = self.period
        self.params['finish_time'] = self.params['start_time'] + self.params['dt'] 

        # We need to reapply the bc
        bc = DirichletBCSet(self)
        bc.add_constant_flow(1, 2.0+1e-10, direction=inflow_direction)
        bc.add_zero_eta(2)
        self.params['bctype'] = 'strong_dirichlet'
        self.params['strong_bc'] = bc
        self.params['free_slip_on_sides'] = True
        self.params['steady_state'] = True
        self.params["newton_solver"] = True 
        self.params["initial_condition"] = ConstantFlowInitialCondition 
        self.turbine_friction = turbine_friction


    def set_turbine_pos(self, position):
        ''' Sets the turbine position and a equal friction parameter. '''
        super(ScenarioConfiguration, self).set_turbine_pos(position, self.turbine_friction)

    def set_site_dimensions(self, site_x_start, site_x_end, site_y_start, site_y_end):
        if not site_x_start < site_x_end or not site_y_start < site_y_end:
            raise ValueError, "Site must have a positive area"
        self.domain.site_x_start = site_x_start
        self.domain.site_y_start = site_y_start
        self.domain.site_x_end = site_x_end
        self.domain.site_y_end = site_y_end


class SinusoidalScenarioConfiguration(ScenarioConfiguration):
    def __init__(self, mesh_file, inflow_direction, finite_element = finite_elements.p2p1, period = 12.*60*60):
        super(SinusoidalScenarioConfiguration, self).__init__(mesh_file, inflow_direction, finite_element)
        self.params['steady_state'] = False
        self.params['functional_final_time_only'] = False

        # Without the 1e-10, the adjoint model hangs! Why? No idea!
        self.params['eta0'] = (2.0+1e-10)/sqrt(self.params["g"]/self.params["depth"]) # This will give a inflow velocity of 2m/s

        # Timing settings
        self.period = period 
        self.params['k'] = 2*pi/(self.period*sqrt(self.params['g']*self.params['depth']))
        self.params['theta'] = 1.0
        self.params['start_time'] = 1./4*self.period
        self.params['dt'] = self.period/50
        self.params['finish_time'] = 5./4*self.period
        info('Wave period (in h): %f' % (self.period/60/60) )
        info('Approximate CFL number (assuming a velocity of 2): ' + str(2*self.params['dt']/self.domain.mesh.hmin()))

        bc = DirichletBCSet(self)
        expression = Expression(("eta0*sqrt(g/depth)*cos(k*x[0]-sqrt(g*depth)*k*t)", "0"), eta0 = self.params["eta0"], g = self.params["g"], depth = self.params["depth"], t = self.params["current_time"], k = self.params["k"])
        bc.add_analytic_u(1, expression)
        bc.add_analytic_u(2, expression)
        bc.add_noslip_u(3)
        self.params['strong_bc'] = bc