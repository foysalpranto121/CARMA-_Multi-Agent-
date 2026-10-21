"""State estimator — infers the current process state from a prefix trace."""

from .replay import ProcessState, estimate_state

__all__ = ['ProcessState', 'estimate_state']
