import sys
import configuration 
import function_spaces
import shallow_water_model as sw_model
from dolfin import *
from dolfin_adjoint import *
from math import log

set_log_level(PROGRESS)
parameters["std_out_all_processes"] = False;
info("Test")

def error(config):
  W = function_spaces.p2p1(config.mesh)
  state = Function(W)
  state.interpolate(config.get_sin_initial_condition()())
  u_exact = "eta0*sqrt(g*depth) * cos(k*x[0]-sqrt(g*depth)*k*t)" # The analytical veclocity of the shallow water equations has been multiplied by depth to account for the change of variable (\tilde u = depth u) in this code.
  ddu_exact = "(diffusion_coef * eta0*sqrt(g*depth) * cos(k*x[0]-sqrt(g*depth)*k*t) * k*k)"
  eta_exact = "eta0*cos(k*x[0]-sqrt(g*depth)*k*t)"
  # The source term
  source = Expression((ddu_exact, 
                       "0.0"), \
                       eta0=config.params["eta0"], g=config.params["g"], \
                       depth=config.params["depth"], t=config.params["current_time"], \
                       k=config.params["k"], friction = config.params["friction"], \
                       diffusion_coef=config.params["diffusion_coef"])

  sw_model.sw_solve(W, config, state, annotate=False, u_source = source)

  analytic_sol = Expression((u_exact, \
                             "0", \
                             eta_exact), \
                             eta0=config.params["eta0"], g=config.params["g"], \
                             depth=config.params["depth"], t=config.params["current_time"], k=config.params["k"])
  exactstate = Function(W)
  exactstate.interpolate(analytic_sol)
  e = state - exactstate
  return sqrt(assemble(dot(e,e)*dx))

def test(refinment_level):
  config = configuration.DefaultConfiguration(nx=16*2**refinment_level, ny=2**refinment_level) 
  config.params["finish_time"] = pi/(sqrt(config.params["g"]*config.params["depth"])*config.params["k"])/20
  config.params["dt"] = config.params["finish_time"]/60
  config.params["dump_period"] = 100000
  config.params["include_diffusion"] = True
  config.params["diffusion_coef"] = 10.0

  return error(config)

errors = []
tests = 4
for refinment_level in range(1, tests):
  errors.append(test(refinment_level))
# Compute the order of convergence 
conv = [] 
for i in range(len(errors)-1):
  conv.append(abs(log(errors[i+1]/errors[i], 2)))

info("Spatial order of convergence (expecting 2.0): %s" % str(conv))
if min(conv)<1.8:
  info_red("Spatial convergence test failed for wave_flather")
  sys.exit(1)
else:
  info_green("Test passed")
