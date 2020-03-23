"""This script is a test that fails when PEARL performance is too low."""
import pytest
try:
    # pylint: disable=unused-import
    import mujoco_py  # noqa: F401
except ImportError:
    pytest.skip('To use mujoco-based features, please install garage[mujoco].',
                allow_module_level=True)
except Exception:  # pylint: disable=broad-except
    pytest.skip(
        'Skipping tests, failed to import mujoco. Do you have a '
        'valid mujoco key installed?',
        allow_module_level=True)
from metaworld.benchmarks import ML1  # noqa: I100

from garage.envs import GarageEnv, normalize
from garage.experiment import LocalRunner, MetaEvaluator
from garage.experiment.deterministic import set_seed
from garage.experiment.task_sampler import SetTaskSampler
from garage.sampler import LocalSampler
from garage.torch.algos import PEARL
from garage.torch.algos.pearl import PEARLWorker
from garage.torch.embeddings import MLPEncoder
from garage.torch.policies import (ContextConditionedPolicy,
                                   TanhGaussianMLPPolicy)
from garage.torch.q_functions import ContinuousMLPQFunction
import garage.torch.utils as tu
from tests.fixtures import snapshot_config


class TestPEARL:
    """Test class for PEARL."""

    def test_pearl_ml1_push(self):
        """Test PEARL with ML1 Push environment."""
        params = dict(seed=1,
                      num_epochs=1,
                      num_train_tasks=50,
                      num_test_tasks=10,
                      latent_size=7,
                      encoder_hidden_sizes=[200, 200, 200],
                      net_size=300,
                      meta_batch_size=16,
                      num_steps_per_epoch=400,
                      num_initial_steps=400,
                      num_tasks_sample=15,
                      num_steps_prior=150,
                      num_extra_rl_steps_posterior=150,
                      batch_size=256,
                      embedding_batch_size=64,
                      embedding_mini_batch_size=64,
                      max_path_length=50,
                      reward_scale=10.,
                      use_information_bottleneck=True,
                      use_next_obs_in_context=False,
                      use_gpu=False)

        net_size = params['net_size']
        set_seed(params['seed'])
        env_sampler = SetTaskSampler(lambda: GarageEnv(
            normalize(ML1.get_train_tasks('push-v1'))))
        env = env_sampler.sample(params['num_train_tasks'])

        test_env_sampler = SetTaskSampler(lambda: GarageEnv(
            normalize(ML1.get_test_tasks('push-v1'))))

        augmented_env = PEARL.augment_env_spec(env[0](), params['latent_size'])
        qf = ContinuousMLPQFunction(
            env_spec=augmented_env,
            hidden_sizes=[net_size, net_size, net_size])

        vf_env = PEARL.get_env_spec(env[0](), params['latent_size'], 'vf')
        vf = ContinuousMLPQFunction(
            env_spec=vf_env, hidden_sizes=[net_size, net_size, net_size])

        inner_policy = TanhGaussianMLPPolicy(
            env_spec=augmented_env,
            hidden_sizes=[net_size, net_size, net_size])

        pearl = PEARL(
            env=env,
            policy_class=ContextConditionedPolicy,
            encoder_class=MLPEncoder,
            inner_policy=inner_policy,
            qf=qf,
            vf=vf,
            num_train_tasks=params['num_train_tasks'],
            num_test_tasks=params['num_test_tasks'],
            latent_dim=params['latent_size'],
            encoder_hidden_sizes=params['encoder_hidden_sizes'],
            meta_batch_size=params['meta_batch_size'],
            num_steps_per_epoch=params['num_steps_per_epoch'],
            num_initial_steps=params['num_initial_steps'],
            num_tasks_sample=params['num_tasks_sample'],
            num_steps_prior=params['num_steps_prior'],
            num_extra_rl_steps_posterior=params[
                'num_extra_rl_steps_posterior'],
            batch_size=params['batch_size'],
            embedding_batch_size=params['embedding_batch_size'],
            embedding_mini_batch_size=params['embedding_mini_batch_size'],
            max_path_length=params['max_path_length'],
            reward_scale=params['reward_scale'],
        )

        tu.set_gpu_mode(params['use_gpu'], gpu_id=0)
        if params['use_gpu']:
            pearl.to()

        runner = LocalRunner(snapshot_config)
        runner.setup(
            algo=pearl,
            env=env[0](),
            sampler_cls=LocalSampler,
            sampler_args=dict(max_path_length=params['max_path_length']),
            n_workers=1,
            worker_class=PEARLWorker)

        worker_args = dict(deterministic=True, accum_context=True)
        meta_evaluator = MetaEvaluator(
            test_task_sampler=test_env_sampler,
            max_path_length=params['max_path_length'],
            worker_class=PEARLWorker,
            worker_args=worker_args,
            n_test_tasks=params['num_test_tasks'])
        pearl.evaluator = meta_evaluator
        runner.train(n_epochs=params['num_epochs'],
                     batch_size=params['batch_size'])
