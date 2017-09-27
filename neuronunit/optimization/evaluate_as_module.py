##
# Assumption that this file was executed after first executing the bash: ipcluster start -n 8 --profile=default &
##



import os
from neuronunit.models import backends
import neuronunit
print(neuronunit.models.__file__)
from neuronunit.models.reduced import ReducedModel
import get_neab
from ipyparallel import depend, require, dependent

model = ReducedModel(get_neab.LEMS_MODEL_PATH,name='vanilla',backend='NEURON')
model.load_model()


class Individual(object):
    '''
    When instanced the object from this class is used as one unit of chromosome or allele by DEAP.
    Extends list via polymorphism.
    '''
    def __init__(self, *args):
        list.__init__(self, *args)
        self.error=None
        self.results=None
        self.name=''
        self.attrs = {}
        self.params=None
        self.score=None
        self.fitness=None
        self.lookup={}
        self.rheobase=None
        self.fitness = creator.FitnessMin
@require('numpy, model_parameters, deap','random')
def import_list(ipp):
    Individual = ipp.Reference('Individual')
    from deap import base, creator, tools
    import deap
    import random
    history = deap.tools.History()
    toolbox = base.Toolbox()
    import model_parameters as modelp
    import numpy as np
    sub_set = []
    whole_BOUND_LOW = [ np.min(i) for i in modelp.model_params.values() ]
    whole_BOUND_UP = [ np.max(i) for i in modelp.model_params.values() ]
    BOUND_LOW = whole_BOUND_LOW
    BOUND_UP = whole_BOUND_UP
    NDIM = len(BOUND_UP)#+1
    def uniform(low, up, size=None):
        try:
            return [random.uniform(a, b) for a, b in zip(low, up)]
        except TypeError:
            return [random.uniform(a, b) for a, b in zip([low] * size, [up] * size)]
    # weights vector should compliment a numpy matrix of eigenvalues and other values
    creator.create("FitnessMin", base.Fitness, weights=(-1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0))
    creator.create("Individual", list, fitness=creator.FitnessMin)
    toolbox.register("attr_float", uniform, BOUND_LOW, BOUND_UP, NDIM)
    toolbox.register("individual", tools.initIterate, creator.Individual, toolbox.attr_float)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)
    toolbox.register("select", tools.selNSGA2)
    toolbox.register("mate", tools.cxSimulatedBinaryBounded, low=BOUND_LOW, up=BOUND_UP, eta=30.0)
    toolbox.register("mutate", tools.mutPolynomialBounded, low=BOUND_LOW, up=BOUND_UP, eta=20.0, indpb=1.0/NDIM)
    return toolbox, tools, history, creator, base

def get_trans_dict(param_dict):
    trans_dict = {}
    for i,k in enumerate(list(param_dict.keys())):
        trans_dict[i]=k
    return trans_dict


def dt_to_ind(dtc,td):
    '''
    Re instanting data transport container at every update dtcpop
    is Noneifying its score attribute, and possibly causing a
    performance bottle neck.
    '''
    ind =[]
    for k in td.keys():
        ind.append(dtc.attrs[td[k]])
    ind.append(dtc.rheobase)
    return ind


class DataTC(object):
    '''
    Data Transport Vessel

    This Object class serves as a data type for storing rheobase search
    attributes and apriori model parameters,
    with the distinction that unlike the NEURON model this class
    can be cheaply transported across HOSTS/CPUs
    '''
    def __init__(self):
        self.lookup = {}
        self.rheobase = None
        self.previous = 0
        self.run_number = 0
        self.attrs = None
        self.steps = None
        self.name = None
        self.results = None
        self.fitness = None
        self.score = None
        self.boolean = False
        self.initiated = False
        self.delta = []
        self.evaluated = False
        self.results = {}
        self.searched = []
        self.searchedd = {}

#@require('numpy', 'copy')
def update_dtc_pop(pop, toolbox, dview, td):
    '''
    inputs a population of genes/alleles, the population size MU, and an optional argument of a rheobase value guess
    outputs a population of genes/alleles, a population of individual object shells, ie a pickleable container for gene attributes.
    Rationale, not every gene value will result in a model for which rheobase is found, in which case that gene is discarded, however to
    compensate for losses in gene population size, more gene samples must be tested for a successful return from a rheobase search.
    If the tests return are successful these new sampled individuals are appended to the population, and then their attributes are mapped onto
    corresponding virtual model objects.
    '''
    import copy
    import numpy as np
    pop = [toolbox.clone(i) for i in pop ]
    #import evaluate_as_module

    def transform(ind):
        #dtc = evaluate_as_module.DataTC()
        dtc = DataTC()
        print(dtc)
        param_dict = {}
        for i,j in enumerate(ind):
            param_dict[trans_dict[i]] = str(j)
        dtc.attrs = param_dict
        dtc.evaluated = False
        return dtc


    if len(pop) > 0:
        dtcpop = list(dview.map_sync(transform, pop))
        #dtcpop = list(copy.copy(dtcpop))
    else:
        # In this case pop is not really a population but an individual
        # but parsimony of naming variables
        # suggests not to change the variable name to reflect this.
        dtcpop = transform(pop)
    return dtcpop

#dview.apply_sync(p_imports)
#p_imports()

def difference(observation,prediction): # v is a tesst
    '''
    This method does not do what you would think
    from reading it.

    rescaling is the culprit. I suspect I do not
    understand how to rescale one unit with another
    compatible unit.
    '''
    #assert type(score) is not type(None)
    import numpy as np
    print(prediction.keys())
    print(prediction.values())

    # The trick is.
    # prediction always has value. but observation 7 out of 8 times has mean.

    if 'value' in prediction.keys():
        unit_predictions = prediction['value']
        if 'mean' in observation.keys():
            unit_observations = observation['mean']
        elif 'value' in observation.keys():
            unit_observations = observation['value']



    if 'mean' in prediction.keys():
        unit_predictions = score.prediction['mean']
        if 'mean' in observation.keys():
            unit_observations = observation['mean']
        elif 'value' in observation.keys():
            unit_observations = observation['value']

    to_r_s = unit_observations.units
    unit_predictions = unit_predictions.rescale(to_r_s)
    unit_observations = unit_observations.rescale(to_r_s)
    unit_delta = np.abs( np.abs(unit_observations)-np.abs(unit_predictions) )
    return float(unit_delta)

def pre_format(dtc):
    import quantities as pq
    import copy
    vtest = {}
    import get_neab
    tests = get_neab.tests
    for k,v in enumerate(tests):
        vtest[k] = {}
    for k,v in enumerate(tests):
        if k == 1 or k == 2 or k == 3:
            # Negative square pulse current.
            vtest[k]['duration'] = 100 * pq.ms
            vtest[k]['amplitude'] = -10 *pq.pA
            vtest[k]['delay'] = 30 * pq.ms

        if k == 0 or k == 4 or k == 5 or k == 6 or k == 7:
            # Threshold current.
            vtest[k]['duration'] = 1000 * pq.ms
            vtest[k]['amplitude'] = dtc.rheobase * pq.pA
            vtest[k]['delay'] = 100 * pq.ms
    return vtest
#@require('quantities','numpy','get_neab','quanitites')



def pre_format(dtc):
    import quantities as pq
    import copy
    dtc.vtest = None
    dtc.vtest = {}
    import get_neab
    tests = get_neab.tests
    for k,v in enumerate(tests):
        dtc.vtest[k] = {}
        dtc.vtest[k]['injected_square_current'] = {}
    for k,v in enumerate(tests):
        if k == 1 or k == 2 or k == 3:
            # Negative square pulse current.
            dtc.vtest[k]['injected_square_current']['duration'] = 100 * pq.ms
            dtc.vtest[k]['injected_square_current']['amplitude'] = -10 *pq.pA
            dtc.vtest[k]['injected_square_current']['delay'] = 30 * pq.ms

        if k == 0 or k == 4 or k == 5 or k == 6 or k == 7:
            # Threshold current.
            dtc.vtest[k]['injected_square_current']['duration'] = 1000 * pq.ms
            dtc.vtest[k]['injected_square_current']['amplitude'] = dtc.rheobase['value']
            dtc.vtest[k]['injected_square_current']['delay'] = 100 * pq.ms
    return dtc



def evaluate(dtc,weight_matrix = None):#This method must be pickle-able for ipyparallel to work.
    '''
    Inputs: An individual gene from the population that has compound parameters, and a tuple iterator that
    is a virtual model object containing an appropriate parameter set, zipped togethor with an appropriate rheobase
    value, that was found in a previous rheobase search.

    outputs: a tuple that is a compound error function that NSGA can act on.

    Assumes rheobase for each individual virtual model object (dtc) has already been found
    there should be a check for dtc.rheobase, and if not then error.
    Inputs a gene and a virtual model object.
    outputs are error components.
    '''

    from neuronunit.models import backends
    from neuronunit.models.reduced import ReducedModel
    import quantities as pq
    import numpy as np
    #import unittest
    #tc = unittest.TestCase('__init__')
    model = ReducedModel(get_neab.LEMS_MODEL_PATH,name=str('vanilla'),backend='NEURON')
    model.load_model()
    assert type(dtc.rheobase) is not type(None)
    #tests = get_neab.suite.tests
    model.set_attrs(attrs = dtc.attrs)
    model.rheobase = dtc.rheobase['value']
    #get_neab.tests[0].prediction = dtc.rheobase

    import copy
    tests = copy.copy(get_neab.tests)
    pre_fitness = []
    fitness = []
    differences = []
    fitness1 = []

    if float(dtc.rheobase) <= 0.0:
        fitness1 = [ 125.0 for i in tests ]



    elif float(dtc.rheobase) > 0.0:
        for k,v in enumerate(tests):

            '''
            Spike width tests and amplitude tests assume a rheobase current injection which does not seem
            to be happening.
            '''
            if k == 1 or k == 2 or k == 3:
                # Negative square pulse current.
                v.params['injected_square_current']['duration'] = 100 * pq.ms
                v.params['injected_square_current']['amplitude'] = -10 *pq.pA
                v.params['injected_square_current']['delay'] = 30 * pq.ms

            if k == 0 or k == 4 or k == 5 or k == 6 or k == 7:
                # Threshold current.
                v.params['injected_square_current']['duration'] = 1000 * pq.ms
                v.params['injected_square_current']['amplitude'] = dtc.rheobase['value']
                v.params['injected_square_current']['delay'] = 100 * pq.ms

            vtests = pre_format(copy.copy(dtc))
            for key, value in vtests[k].items():
                print('broken')
                print(key,value,v.params)
                #v.params['injected_square_current'][key] = value
            #vtest[k] = {}
            if k == 0:
                v.prediction = None
                v.prediction = {}
                v.prediction['value'] = dtc.rheobase['value']

            assert type(model) is not type(None)
            score = v.judge(model,stop_on_error = False, deep_error = True)

            #if type(v.prediction) is type(None):
            #    import pdb; pdb.set_trace()
            if type(v.prediction) is not type(None):
                differences.append(difference(v))
                pre_fitness.append(float(score.sort_key))
            else:
                differences.append(None)
                pre_fitness.append(125.0)

            model.run_number += 1
            #dtc.results[t]
    # outside of the test iteration block.
        for k,f in enumerate(copy.copy(pre_fitness)):

            fitness1.append(difference(v))

            if k == 5:
                from neuronunit import capabilities
                ans = model.get_membrane_potential()
                sw = capabilities.spikes2widths(ans)
                unit_observations = tests[5].observation['mean']

                #unit_observations = v.observation['value']
                to_r_s = unit_observations.units
                unit_predictions  = float(sw.rescale(to_r_s))
                fitness1[5] = float(np.abs( np.abs(float(unit_observations))-np.abs(float(unit_predictions))))
                #fitness1[5] = unit_delta
            if k == 0:
                fitness1.append(differences[0])
            if differences[0] > 10.0:
                if k != 0:
                    #fitness1.append(pre_fitness[k])
                    fitness1.append(pre_fitness[k] + 1.5 * differences[0] ) # add the rheobase error to all the errors.
                    assert fitness1[k] != pre_fitness[k]
            else:
                fitness1.append(pre_fitness[k])
            if k == 1:
                fitness1.append(differences[1])
            if differences[1] > 10.0 :
                if k != 1 and len(fitness1)>1 :
                    #fitness1.append(pre_fitness[k])
                    fitness1.append(pre_fitness[k] + 1.25 * differences[1] ) # add the rheobase error to all the errors.
                    assert fitness1[k] != pre_fitness[k]
    pre_fitness = []
    return fitness1[0],fitness1[1],\
           fitness1[2],fitness1[3],\
           fitness1[4],fitness1[5],\
           fitness1[6],fitness1[7],



def cache_sim_runs(dtc):
    '''
    This could be used to stop neuronunit tests
    from rerunning the same current injection set on the same
    set of parameters
    '''
    from neuronunit.models import backends
    from neuronunit.models.reduced import ReducedModel
    import quantities as pq
    import numpy as np
    import get_neab

    import copy
    # copying here is critical for get_neab
    tests = copy.copy(get_neab.tests)
    #from itertools import repeat
    vtests = pre_format(copy.copy(dtc))
    tests[0].prediction = {}
    tests[0].prediction['value'] = dtc.rheobase * pq.pA

    if float(dtc.rheobase) > 0.0:
        for k,t in enumerate(tests):
            '''
            can tests be re written such that it is more closure compatible?
            '''
            t.params = {}
            t.params['injected_square_current'] = {}
            t.params['injected_square_current']['duration'] = None
            t.params['injected_square_current']['amplitude'] = None
            t.params['injected_square_current']['delay'] = None

            for key, value in vtests[k].items():
                t.params['injected_square_current'][key] = value


            if k == 0:
                tests[k].prediction = {}
                tests[k].prediction['value'] = dtc.rheobase * pq.pA

            #new_file_path = str(get_neab.LEMS_MODEL_PATH)+str(os.getpid())
            model = ReducedModel(get_neab.LEMS_MODEL_PATH,name=str('vanilla'),backend='NEURON')
            model.load_model()
            model.set_attrs(attrs = dtc.attrs)
            # check if these attributes have been evaluated before.
            if str(dtc.attrs) in model.lookup.keys:
                return dtc
            else:

                print(t,model,'within pre evaluate, eam')

                score = t.judge(model,stop_on_error = False, deep_error = True)
                print(score,'within pre evaluate, eam')

                print(model.get_spike_count())
                print(type(v_m),'within pre evaluate, eam')

                v_m = model.get_membrane_potential()
                print(type(v_m),'within pre evaluate, eam')
                if 't' not in dtc.results.keys():
                    dtc.results[t] = {}
                    dtc.results[t]['v_m'] = v_m
                elif 't' in dtc.results.keys():
                    dtc.results[t]['v_m'] = v_m
                dtc.lookup[str(dtc.attrs)] = dtc.results
    return dtc

#from scoop import futures


def get_trans_dict(param_dict):
    trans_dict = {}
    for i,k in enumerate(list(param_dict.keys())):
        trans_dict[i]=k
    return trans_dict
import model_parameters
param_dict = model_parameters.model_params

def dtc_to_ind(dtc,td):
    '''
    Re instanting Virtual Model at every update dtcpop
    is Noneifying its score attribute, and possibly causing a
    performance bottle neck.
    '''

    ind =[]
    for k in td.keys():
        ind.append(dtc.attrs[td[k]])
    ind.append(dtc.rheobase)
    return ind


#dtcpop = evaluate_as_module.update_dtc_pop(pop, toolbox, dview, td)

def update_dtc_pop(pop, toolbox, dview, trans_dict):
    '''
    inputs a population of genes/alleles, the population size MU, and an optional argument of a rheobase value guess
    outputs a population of genes/alleles, a population of individual object shells, ie a pickleable container for gene attributes.
    Rationale, not every gene value will result in a model for which rheobase is found, in which case that gene is discarded, however to
    compensate for losses in gene population size, more gene samples must be tested for a successful return from a rheobase search.
    If the tests return are successful these new sampled individuals are appended to the population, and then their attributes are mapped onto
    corresponding virtual model objects.
    '''
    #from itertools import repeat
    import numpy as np
    import copy
    pop = [toolbox.clone(i) for i in pop ]
    #import utilities
    def transform(ind):
        '''
        Re instanting Virtual Model at every update dtcpop
        is Noneifying its score attribute, and possibly causing a
        performance bottle neck.
        '''
        dtc = DataTC()

        param_dict = {}
        for i,j in enumerate(ind):
            param_dict[trans_dict[i]] = str(j)
        dtc.attrs = param_dict
        dtc.name = dtc.attrs
        dtc.evaluated = False
        return dtc


    if len(pop) > 0:
        dtcpop = dview.map_sync(transform, pop)
        dtcpop = list(copy.copy(dtcpop))
    else:
        # In this case pop is not really a population but an individual
        # but parsimony of naming variables
        # suggests not to change the variable name to reflect this.
        dtcpop = transform(pop)
    return dtcpop
