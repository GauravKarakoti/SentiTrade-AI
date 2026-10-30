// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/extensions/ERC4626.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

interface ISSIProtocol {
    function mint(address indexToken, uint256 amount) external returns (uint256);
    function redeem(address indexToken, uint256 shares) external returns (uint256);
}

contract SentiTradeVault is ERC4626, Ownable {
    ISSIProtocol public ssiRouter;

    // Whitelisted SSI Index Tokens
    mapping(address => bool) public approvedIndices;

    // --- Wave 3 Builder Race: SoDEX Builder Code & On-Chain Fee Revenue ---
    string public sodexBuilderCode = "SENTITRADE";
    uint256 public builderFeeBps = 10; // 10 bps = 0.10%
    address public builderFeeTreasury;
    uint256 public totalBuilderFeeRevenue;
    uint256 public totalRebalanceVolume;

    event Rebalanced(
        address indexed indexToken,
        uint256 amountIn,
        uint256 builderFee,
        string action,
        string builderCode
    );
    event BuilderFeeCollected(address indexed caller, uint256 feeAmount, string builderCode);
    event BuilderConfigUpdated(string builderCode, uint256 feeBps, address treasury);

    constructor(
        IERC20 _asset,
        address _ssiRouter
    ) ERC4626(_asset) ERC20("SentiTrade AI Vault", "vSENTI") Ownable(msg.sender) {
        ssiRouter = ISSIProtocol(_ssiRouter);
        builderFeeTreasury = msg.sender;
    }

    // Restricts execution to vSENTI holders or the system owner
    modifier onlyShareholderOrOwner() {
        require(balanceOf(msg.sender) > 0 || msg.sender == owner(), "Not authorized: Must hold vSENTI shares");
        _;
    }

    function setApprovedIndex(address _index, bool _status) external onlyOwner {
        approvedIndices[_index] = _status;
    }

    function setBuilderConfig(
        string calldata _builderCode,
        uint256 _feeBps,
        address _treasury
    ) external onlyOwner {
        require(_feeBps <= 100, "Builder fee cannot exceed 100 bps (1%)");
        require(_treasury != address(0), "Invalid treasury address");
        sodexBuilderCode = _builderCode;
        builderFeeBps = _feeBps;
        builderFeeTreasury = _treasury;
        emit BuilderConfigUpdated(_builderCode, _feeBps, _treasury);
    }

    function executeBullishRebalance(address indexToken, uint256 assetAmount) external onlyShareholderOrOwner {
        require(approvedIndices[indexToken], "Index not approved");
        require(assetAmount > 0, "Amount must be > 0");

        uint256 fee = (assetAmount * builderFeeBps) / 10000;
        uint256 netAmount = assetAmount - fee;

        if (fee > 0 && builderFeeTreasury != address(0)) {
            IERC20(asset()).transfer(builderFeeTreasury, fee);
            totalBuilderFeeRevenue += fee;
            emit BuilderFeeCollected(msg.sender, fee, sodexBuilderCode);
        }

        totalRebalanceVolume += assetAmount;

        // Approve router to spend vault's net idle USDC
        IERC20(asset()).approve(address(ssiRouter), netAmount);
        ssiRouter.mint(indexToken, netAmount);

        emit Rebalanced(indexToken, netAmount, fee, "BUY_INDEX", sodexBuilderCode);
    }

    function executeBearishRebalance(address indexToken, uint256 indexShares) external onlyShareholderOrOwner {
        require(approvedIndices[indexToken], "Index not approved");
        require(indexShares > 0, "Shares must be > 0");

        // Redeem SSI index token back for USDC
        IERC20(indexToken).approve(address(ssiRouter), indexShares);
        uint256 redeemedUsdc = ssiRouter.redeem(indexToken, indexShares);

        uint256 fee = (redeemedUsdc * builderFeeBps) / 10000;
        if (fee > 0 && builderFeeTreasury != address(0)) {
            IERC20(asset()).transfer(builderFeeTreasury, fee);
            totalBuilderFeeRevenue += fee;
            emit BuilderFeeCollected(msg.sender, fee, sodexBuilderCode);
        }

        totalRebalanceVolume += redeemedUsdc;

        emit Rebalanced(indexToken, indexShares, fee, "SELL_INDEX", sodexBuilderCode);
    }
}