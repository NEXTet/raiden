# -*- coding: utf-8 -*-
# pylint: disable=too-few-public-methods,too-many-arguments,too-many-instance-attributes
from ethereum.utils import encode_hex

from raiden.transfer.architecture import State
from raiden.utils import pex, sha3, typing
from raiden.transfer.state import (
    EMPTY_MERKLE_ROOT,
    BalanceProofSignedState,
    BalanceProofUnsignedState,
    HashTimeLockState,
)


def lockedtransfersigned_from_message(message):
    """ Create LockedTransferSignedState from a LockedTransfer message. """
    balance_proof = BalanceProofSignedState(
        message.nonce,
        message.transferred_amount,
        message.locksroot,
        message.channel,
        message.message_hash,
        message.signature,
        message.sender,
    )

    lock = HashTimeLockState(
        message.lock.amount,
        message.lock.expiration,
        message.lock.secrethash,
    )

    transfer_state = LockedTransferSignedState(
        message.identifier,
        message.token,
        balance_proof,
        lock,
        message.initiator,
        message.target,
    )

    return transfer_state


class InitiatorPaymentState(State):
    """ State of a payment for the initiator node.
    A single payment may have multiple transfers. E.g. because if one of the
    transfers fails or timeouts another transfer will be started with a
    different secrethash.
    """
    __slots__ = (
        'initiator',
        'cancelled_channels',
    )

    def __init__(self, initiator: typing.Address):
        # TODO: Allow multiple concurrent transfers and unlock refunds (issue #1091).
        self.initiator = initiator
        self.cancelled_channels = list()

    def __repr__(self):
        return '<InitiatorPaymentState initiator:{}>'.format(
            self.initiator,
        )

    def __eq__(self, other):
        return (
            isinstance(other, InitiatorPaymentState) and
            self.initiator == other.initiator and
            self.cancelled_channels == other.cancelled_channels
        )

    def __ne__(self, other):
        return not self.__eq__(other)


class InitiatorTransferState(State):
    """ State of a transfer for the initiator node. """

    __slots__ = (
        'transfer_description',
        'channel_identifier',
        'transfer',
        'secretrequest',
        'revealsecret',
    )

    def __init__(
            self,
            transfer_description: 'TransferDescriptionWithSecretState',
            channel_identifier):

        if not isinstance(transfer_description, TransferDescriptionWithSecretState):
            raise ValueError(
                'transfer_description must be an instance of TransferDescriptionWithSecretState'
            )

        # This is the users description of the transfer. It does not contain a
        # balance proof and it's not related to any channel.
        self.transfer_description = transfer_description

        # This it the channel used to satisfy the above transfer.
        self.channel_identifier = channel_identifier
        self.transfer = None
        self.secretrequest = None
        self.revealsecret = None

    def __repr__(self):
        return '<InitiatorTransferState transfer:{} channel:{}>'.format(
            self.transfer,
            pex(self.channel_identifier),
        )

    def __eq__(self, other):
        return (
            isinstance(other, InitiatorTransferState) and
            self.transfer_description == other.transfer_description and
            self.channel_identifier == other.channel_identifier and
            self.transfer == other.transfer and
            self.secretrequest == other.secretrequest and
            self.revealsecret == other.revealsecret
        )

    def __ne__(self, other):
        return not self.__eq__(other)


class MediatorTransferState(State):
    """ State of a transfer for the mediator node.
    A mediator may manage multiple channels because of refunds, but all these
    channels will be used for the same transfer (not for different payments).
    Args:
        secrethash: The secrethash used for this transfer.
    """

    __slots__ = (
        'secrethash',
        'secret',
        'transfers_pair',
    )

    def __init__(self, secrethash: typing.Keccak256):
        # for convenience
        self.secrethash = secrethash
        self.secret = None
        self.transfers_pair = list()

    def __repr__(self):
        return '<MediatorTransferState secrethash:{} qtd_transfers:{}>'.format(
            pex(self.secrethash),
            len(self.transfers_pair),
        )

    def __eq__(self, other):
        return (
            isinstance(other, MediatorTransferState) and
            self.secrethash == other.secrethash and
            self.secret == other.secret and
            self.transfers_pair == other.transfers_pair
        )

    def __ne__(self, other):
        return not self.__eq__(other)


class TargetTransferState(State):
    """ State of a transfer for the target node. """

    __slots__ = (
        'route',
        'transfer',
        'secret',
        'hahslock',
        'state',
    )

    valid_states = (
        'secret_request',
        'reveal_secret',
        'waiting_close',
        'expired',
    )

    def __init__(self, route: 'RouteState', transfer: 'LockedTransferSignedState'):
        self.route = route
        self.transfer = transfer

        self.secret = None
        self.state = 'secret_request'

    def __repr__(self):
        return '<TargetTransferState transfer:{} state:{}>'.format(
            self.transfer,
            self.state,
        )

    def __eq__(self, other):
        return (
            isinstance(other, TargetTransferState) and
            self.route == other.route and
            self.transfer == other.transfer and
            self.secret == other.secret and
            self.state == other.state
        )

    def __ne__(self, other):
        return not self.__eq__(other)


class LockedTransferUnsignedState(State):
    """ State for a transfer created by the local node which contains a hash
    time lock and may be sent.
    """

    __slots__ = (
        'identifier',
        'token',
        'balance_proof',
        'lock',
        'initiator',
        'target',
    )

    def __init__(
            self,
            identifier,
            token: typing.Address,
            balance_proof: BalanceProofUnsignedState,
            lock: HashTimeLockState,
            initiator: typing.Address,
            target: typing.Address):

        if not isinstance(lock, HashTimeLockState):
            raise ValueError('lock must be a HashTimeLockState instance')

        if not isinstance(balance_proof, BalanceProofUnsignedState):
            raise ValueError('balance_proof must be a BalanceProofUnsignedState instance')

        # At least the lock for this transfer must be in the locksroot, so it
        # must not be empty
        if balance_proof.locksroot is EMPTY_MERKLE_ROOT:
            raise ValueError('balance_proof must not be empty')

        self.identifier = identifier
        self.token = token
        self.balance_proof = balance_proof
        self.lock = lock
        self.initiator = initiator
        self.target = target

    def __repr__(self):
        return (
            '<LockedTransferUnsignedState id:{} token:{} lock:{} target:{}>'
        ).format(
            self.identifier,
            encode_hex(self.token),
            self.lock,
            encode_hex(self.target),
        )

    def __eq__(self, other):
        return (
            isinstance(other, LockedTransferUnsignedState) and
            self.identifier == other.identifier and
            self.token == other.token and
            self.balance_proof == other.balance_proof and
            self.lock == other.lock and
            self.initiator == other.initiator and
            self.target == other.target
        )

    def __ne__(self, other):
        return not self.__eq__(other)


class LockedTransferSignedState(State):
    """ State for a received transfer which contains a hash time lock and a
    signed balance proof.
    """

    __slots__ = (
        'identifier',
        'token',
        'balance_proof',
        'lock',
        'initiator',
        'target',
    )

    def __init__(
            self,
            identifier,
            token: typing.Address,
            balance_proof: BalanceProofSignedState,
            lock: HashTimeLockState,
            initiator: typing.Address,
            target: typing.Address):

        if not isinstance(lock, HashTimeLockState):
            raise ValueError('lock must be a HashTimeLockState instance')

        if not isinstance(balance_proof, BalanceProofSignedState):
            raise ValueError('balance_proof must be a BalanceProofSignedState instance')

        # At least the lock for this transfer must be in the locksroot, so it
        # must not be empty
        if balance_proof.locksroot is EMPTY_MERKLE_ROOT:
            raise ValueError('balance_proof must not be empty')

        self.identifier = identifier
        self.token = token
        self.balance_proof = balance_proof
        self.lock = lock
        self.initiator = initiator
        self.target = target

    def __repr__(self):
        return (
            '<LockedTransferSignedState id:{} token:{} lock:{} target:{}>'
        ).format(
            self.identifier,
            encode_hex(self.token),
            self.lock,
            encode_hex(self.target),
        )

    def __eq__(self, other):
        return (
            isinstance(other, LockedTransferSignedState) and
            self.identifier == other.identifier and
            self.token == other.token and
            self.balance_proof == other.balance_proof and
            self.lock == other.lock and
            self.initiator == other.initiator and
            self.target == other.target
        )

    def __ne__(self, other):
        return not self.__eq__(other)


class TransferDescriptionWithSecretState(State):
    """ Describes a transfer (target, amount, and token) and contains an
    additional secret that can be used with a hash-time-lock.
    """

    __slots__ = (
        'identifier',
        'amount',
        'registry',
        'token',
        'initiator',
        'target',
        'secret',
        'secrethash',
    )

    def __init__(
            self,
            identifier,
            amount: typing.TokenAmount,
            registry: typing.Address,
            token: typing.Address,
            initiator: typing.Address,
            target: typing.Address,
            secret: typing.Secret):

        secrethash = sha3(secret)

        self.identifier = identifier
        self.amount = amount
        self.registry = registry
        self.token = token
        self.initiator = initiator
        self.target = target
        self.secret = secret
        self.secrethash = secrethash

    def __repr__(self):
        return (
            '<TransferDescriptionWithSecretState network:{} token:{} amount:{} secrethash:{}>'
        ).format(
            pex(self.registry),
            pex(self.token),
            self.amount,
            pex(self.secrethash),
        )

    def __eq__(self, other):
        return (
            isinstance(other, TransferDescriptionWithSecretState) and
            self.identifier == other.identifier and
            self.amount == other.amount and
            self.registry == other.registry and
            self.token == other.token and
            self.initiator == other.initiator and
            self.target == other.target and
            self.secret == other.secret and
            self.secrethash == other.secrethash
        )

    def __ne__(self, other):
        return not self.__eq__(other)


class MediationPairState(State):
    """ State for a mediated transfer.
    A mediator will pay payee node knowing that there is a payer node to cover
    the token expenses. This state keeps track of the routes and transfer for
    the payer and payee, and the current state of the payment.
    """

    __slots__ = (
        'payee_address',
        'payee_transfer',
        'payee_state',
        'payer_transfer',
        'payer_state',
    )

    # payee_pending:
    #   Initial state.
    #
    # payee_secret_revealed:
    #   The payee is following the raiden protocol and has sent a SecretReveal.
    #
    # payee_refund_withdraw:
    #   The corresponding refund transfer was withdrawn on-chain, the payee has
    #   /not/ withdrawn the lock yet, it only learned the secret through the
    #   blockchain.
    #   Note: This state is reachable only if there is a refund transfer, that
    #   is represented by a different MediationPairState, and the refund
    #   transfer is at 'payer_contract_withdraw'.
    #
    # payee_contract_withdraw:
    #   The payee received the token on-chain. A transition to this state is
    #   valid from all but the `payee_expired` state.
    #
    # payee_balance_proof:
    #   This node has sent a SendBalanceProof to the payee with the balance
    #   updated.
    #
    # payee_expired:
    #   The lock has expired.
    valid_payee_states = (
        'payee_pending',
        'payee_secret_revealed',
        'payee_refund_withdraw',
        'payee_contract_withdraw',
        'payee_balance_proof',
        'payee_expired',
    )

    valid_payer_states = (
        'payer_pending',
        'payer_secret_revealed',    # SendRevealSecret was sent
        'payer_waiting_close',      # ContractSendChannelClose was sent
        'payer_waiting_withdraw',   # ContractSendWithdraw was sent
        'payer_contract_withdraw',  # ContractChannelReceiveWithdraw for the above send received
        'payer_balance_proof',      # ReceiveBalanceProof was received
        'payer_expired',            # None of the above happened and the lock expired
    )

    def __init__(
            self,
            payer_transfer: LockedTransferSignedState,
            payee_address: typing.Address,
            payee_transfer: LockedTransferUnsignedState):

        if not isinstance(payer_transfer, LockedTransferSignedState):
            raise ValueError('payer_transfer must be a LockedTransferSignedState instance')

        if not isinstance(payee_address, typing.T_Address):
            raise ValueError('payee_address must be an address')

        if not isinstance(payee_transfer, LockedTransferUnsignedState):
            raise ValueError('payee_transfer must be a LockedTransferUnsignedState instance')

        self.payer_transfer = payer_transfer
        self.payee_address = payee_address
        self.payee_transfer = payee_transfer

        # these transfers are settled on different payment channels. These are
        # the states of each mediated transfer in respect to each channel.
        self.payer_state = 'payer_pending'
        self.payee_state = 'payee_pending'

    def __repr__(self):
        return '<MediationPairState payee:{} {} payer:{}>'.format(
            self.payer_transfer,
            pex(self.payee_address),
            self.payee_transfer,
        )

    def __eq__(self, other):
        return (
            isinstance(other, MediationPairState) and
            self.payee_address == other.payee_address and
            self.payee_transfer == other.payee_transfer and
            self.payee_state == other.payee_state and
            self.payer_transfer == other.payer_transfer and
            self.payer_state == other.payer_state
        )

    def __ne__(self, other):
        return not self.__eq__(other)
