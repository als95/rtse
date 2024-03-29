import os

import utils
import source_mut_operators
import network_triage
import tensorflow as tf
import argparse

class SourceMutatedModelGenerators:

    def __init__(self):
        os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
        self.utils = utils.GeneralUtils()

        self.network = network_triage.TriageNetwork()
        self.source_mut_opts = source_mut_operators.SourceMutationOperators(self.network)
    

    def integration_test(self, verbose=False, start_point=0):
        modes = ['DR', 'LE', 'DM', 'DF', 'NP', 'LR', 'LAs', 'AFRs']

        # Model creation
        # This should variates according to the value of self.model_architecture
        train_dataset, test_dataset = self.network.load_data()
        model = self.network.create_model()

        # Test for generate_model_by_source_mutation function 
        for index, mode in enumerate(modes):
            if index >= int(start_point):
                self.generate_model_by_source_mutation(train_dataset, test_dataset, model, mode, verbose=verbose)


    def generate_model_by_source_mutation(self, train_dataset, test_dataset, model, mode, verbose=False):
        mutated_datas, mutated_labels = None, None
        mutated_model = None
        valid_modes = ['DR', 'LE', 'DM', 'DF', 'NP', 'LR', 'LAs', 'AFRs']
        assert mode in valid_modes, 'Input mode ' + mode + ' is not implemented'
        
        # Parameters can experiment with 
        mutation_ratio = 0.9
        suffix = '_model'
        name_of_saved_file = mode + suffix
        mutated_layer_indices = None

        lower_bound = 0
        upper_bound = 16
        STD = 100

        if mode == 'DR':
            (mutated_datas, mutated_labels), mutated_model = self.source_mut_opts.DR_mut(train_dataset, model, mutation_ratio)
        elif mode == 'LE':
            (mutated_datas, mutated_labels), mutated_model = self.source_mut_opts.LE_mut(train_dataset, model, lower_bound, upper_bound, mutation_ratio)
        elif mode == 'DM':
            (mutated_datas, mutated_labels), mutated_model = self.source_mut_opts.DM_mut(train_dataset, model, mutation_ratio)
        elif mode == 'DF':
            (mutated_datas, mutated_labels), mutated_model = self.source_mut_opts.DF_mut(train_dataset, model, mutation_ratio)
        elif mode == 'NP':
            (mutated_datas, mutated_labels), mutated_model = self.source_mut_opts.NP_mut(train_dataset, model, mutation_ratio, STD=STD)
        elif mode == 'LR':
            (mutated_datas, mutated_labels), mutated_model = self.source_mut_opts.LR_mut(train_dataset, model, mutated_layer_indices=mutated_layer_indices)
        elif mode == 'LAs':
            (mutated_datas, mutated_labels), mutated_model = self.source_mut_opts.LAs_mut(train_dataset, model, mutated_layer_indices=mutated_layer_indices)
        elif mode == 'AFRs':
            (mutated_datas, mutated_labels), mutated_model = self.source_mut_opts.AFRs_mut(train_dataset, model, mutated_layer_indices=mutated_layer_indices)
        else:
            pass 

        mutated_model = self.network.compile_model(mutated_model)
        test_datas, test_labels = test_dataset
        trained_mutated_model = self.network.train_model(mutated_model, mutated_datas, mutated_labels, test_datas, test_labels)
            
        if verbose:
            # Extract unmutated model and dataset for comparision
            train_datas, train_labels = train_dataset
            model = self.network.compile_model(model)
            trained_model = self.network.train_model(model, train_datas, train_labels, test_datas, test_labels)

            self.utils.print_messages_SMO(mode, train_datas=train_datas, train_labels=train_labels, mutated_datas=mutated_datas, mutated_labels=mutated_labels, model=trained_model, mutated_model=trained_mutated_model, mutation_ratio=mutation_ratio)
        
            test_datas, test_labels = test_dataset
            self.network.evaluate_model(trained_model, test_datas, test_labels)
            self.network.evaluate_model(trained_mutated_model, test_datas, test_labels, mode)

        self.network.save_model(trained_mutated_model, name_of_saved_file, mode)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Main function for source mutated model generator")
    parser.add_argument('start_point')

    args = parser.parse_args()

    source_mut_model_generators = SourceMutatedModelGenerators()
    source_mut_model_generators.integration_test(False, args.start_point)