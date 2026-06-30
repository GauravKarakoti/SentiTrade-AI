// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/extensions/ERC4626.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

// FIX: Updated to uint256 to match the actual Router signature
interface ISSIProtocol {
    function mint(address indexToken, uint256 amount) external returns (uint256);
    function redeem(address indexToken, uint256 shares) external returns (uint256);
}

contract SentiTradeVault is ERC4626, Ownable {
    ISSIProtocol public ssiRouter;
    
    // Whitelisted SSI Index Tokens
    mapping(address => bool) public approvedIndices;

    event Rebalanced(address indexed indexToken, uint256 amountIn, string action);

    constructor(
        IERC20 _asset, 
        address _ssiRouter
    ) ERC4626(_asset) ERC20("SentiTrade AI Vault", "vSENTI") Ownable(msg.sender) {
        ssiRouter = ISSIProtocol(_ssiRouter);
    }

    function setApprovedIndex(address _index, bool _status) external onlyOwner {
        approvedIndices[_index] = _status;
    }

    function executeBullishRebalance(address indexToken, uint256 assetAmount) external onlyOwner {
        require(approvedIndices[indexToken], "Index not approved");
        
        // Approve router to spend vault's idle USDC
        IERC20(asset()).approve(address(ssiRouter), assetAmount);
        
        // FIX: Removed the uint200() casting
        ssiRouter.mint(indexToken, assetAmount);
        
        emit Rebalanced(indexToken, assetAmount, "BUY_INDEX");
    }

    function executeBearishRebalance(address indexToken, uint256 indexShares) external onlyOwner {
        require(approvedIndices[indexToken], "Index not approved");
        
        // Redeem SSI index token back for USDC
        IERC20(indexToken).approve(address(ssiRouter), indexShares);
        ssiRouter.redeem(indexToken, indexShares);
        
        emit Rebalanced(indexToken, indexShares, "SELL_INDEX");
    }
}