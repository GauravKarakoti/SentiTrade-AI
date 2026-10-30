import express from 'express';
import { ethers } from 'ethers';
import * as dotenv from 'dotenv';
import VaultABI from './abis/SentiTradeVault.json';

dotenv.config();

const app = express();
app.use(express.json());

const RPC_URL = process.env.BASE_RPC_URL!;
const PRIVATE_KEY = process.env.EXECUTOR_PRIVATE_KEY!;
const VAULT_ADDRESS = process.env.VAULT_ADDRESS!;
const SODEX_BUILDER_CODE = process.env.SODEX_BUILDER_CODE;
const SODEX_BUILDER_FEE_BPS = Number(process.env.SODEX_BUILDER_FEE_BPS || 10);

const SSI_CONTRACTS: Record<string, string> = {
    "$MAG7.ssi": "0x4b54c91aF949F06B853460018CdCd79369F333e4",
    "$DEFI.ssi": "0xdA9f3bdb44B9e2f0A71291ccE879eabD1fF06f2B",
    "$MEME.ssi": "0x26E6800068Ea06D036Ae1C90db0bc1b1a9e3233C"
};

const provider = new ethers.JsonRpcProvider(RPC_URL);
const wallet = new ethers.Wallet(PRIVATE_KEY, provider);
const vaultContract = new ethers.Contract(VAULT_ADDRESS, VaultABI, wallet);

// Health endpoint for GitHub Actions Keep-Alive & Wave 3 Builder Race verification
app.get('/', (_req, res) => {
    return res.json({
        status: "live",
        service: "SentiTrade-AI Vault Execution Node",
        wave: "SoSoValue Buildathon Wave 3 - Builder Race",
        builderCode: SODEX_BUILDER_CODE,
        builderFeeBps: SODEX_BUILDER_FEE_BPS,
        vaultAddress: VAULT_ADDRESS
    });
});

app.get('/api/vault-balance/:address', async (req, res) => {
    try {
        const userAddress = req.params.address;
        if (!ethers.isAddress(userAddress)) {
            return res.status(400).json({ error: "Invalid Ethereum address format." });
        }

        const shareBalance = await vaultContract.balanceOf(userAddress);
        let assetBalance = 0n;
        if (shareBalance > 0n) {
            assetBalance = await vaultContract.convertToAssets(shareBalance);
        }

        return res.json({
            shares: ethers.formatUnits(shareBalance, 6),
            assets: ethers.formatUnits(assetBalance, 6),
            builderCode: SODEX_BUILDER_CODE
        });
    } catch (error: any) {
        console.error(`[Balance Check Failed] ${error.message}`);
        return res.status(500).json({ error: error.message });
    }
});

app.get('/api/vault-status', async (_req, res) => {
    try {
        const USDC_ADDRESS = "0x036CbD53842c5426634e7929541eC2318f3dCF7e";
        const usdcContract = new ethers.Contract(
            USDC_ADDRESS,
            ["function balanceOf(address) view returns(uint256)"],
            provider
        );

        const usdcBalance = await usdcContract.balanceOf(VAULT_ADDRESS);

        let dynamicTotalAssets = usdcBalance;
        const allocations: any[] = [];

        const BASE_NAV_PRICE = 10_000_000n; // 10.00 USDC (6 decimals)

        for (const [name, address] of Object.entries(SSI_CONTRACTS)) {
            const indexContract = new ethers.Contract(
                address,
                ["function balanceOf(address) view returns(uint256)"],
                provider
            );

            const bal = await indexContract.balanceOf(VAULT_ADDRESS);

            if (bal > 0n) {
                const valueInUsdc = (bal * BASE_NAV_PRICE) / (10n ** 18n);

                dynamicTotalAssets += valueInUsdc;

                allocations.push({
                    asset: name,
                    rawUsdcValue: valueInUsdc,
                    value: parseFloat(ethers.formatUnits(valueInUsdc, 6)),
                    currentPrice: 10.00
                });
            }
        }

        for (const alloc of allocations) {
            alloc.percentage = Number((alloc.rawUsdcValue * 100n) / (dynamicTotalAssets > 0n ? dynamicTotalAssets : 1n));
            delete alloc.rawUsdcValue;
        }

        // Fetch on-chain Wave 3 Builder Fee telemetry if supported by deployed contract
        let onChainBuilderFees = 0;
        let onChainRebalanceVol = 0;
        try {
            const rawFees = await vaultContract.totalBuilderFeeRevenue();
            const rawVol = await vaultContract.totalRebalanceVolume();
            onChainBuilderFees = parseFloat(ethers.formatUnits(rawFees, 6));
            onChainRebalanceVol = parseFloat(ethers.formatUnits(rawVol, 6));
        } catch {
            // Safe fallback if contract was deployed prior to Wave 3 ABI addition
        }

        res.json({
            totalAssets: parseFloat(ethers.formatUnits(dynamicTotalAssets, 6)),
            usdcBalance: parseFloat(ethers.formatUnits(usdcBalance, 6)),
            usdcPercentage: Number((usdcBalance * 100n) / (dynamicTotalAssets > 0n ? dynamicTotalAssets : 1n)),
            builderCode: SODEX_BUILDER_CODE,
            builderFeeBps: SODEX_BUILDER_FEE_BPS,
            totalBuilderFeeRevenue: onChainBuilderFees,
            totalRebalanceVolume: onChainRebalanceVol,
            allocations
        });
    } catch (error: any) {
        console.error(`[Vault Status Error] ${error.message}`);
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/execute-rebalance', async (req, res) => {
    const { asset, action, confidence, callerAddress, builderCode } = req.body;
    const activeBuilderCode = builderCode || SODEX_BUILDER_CODE;

    if (confidence < 85) {
        return res.status(400).json({ error: "Confidence too low for rebalance." });
    }

    // --- SECTOR-GATING LOGIC ---
    if (callerAddress) {
        if (!ethers.isAddress(callerAddress)) {
            return res.status(400).json({ error: "Invalid caller Ethereum address format." });
        }

        const shareBalance = await vaultContract.balanceOf(callerAddress);
        if (shareBalance === 0n) {
            return res.status(403).json({ error: "Access Denied: Only vSENTI shareholders can execute vault trades." });
        }
    } else {
        return res.status(403).json({ error: "Access Denied: Caller address missing." });
    }

    const indexAddress = SSI_CONTRACTS[asset];
    if (!indexAddress) {
        return res.status(400).json({ error: `Unrecognized SSI index: ${asset}` });
    }

    try {
        console.log(`[Tx] Initiating Vault Rebalance: ${action} ${asset} by ${callerAddress} [BuilderCode: ${activeBuilderCode}]`);

        let tx;
        let deployedUsdcFormatted = 0;

        if (action === "BUY") {
            const USDC_ADDRESS = "0x036CbD53842c5426634e7929541eC2318f3dCF7e";
            const usdcContract = new ethers.Contract(
                USDC_ADDRESS,
                ["function balanceOf(address) view returns(uint256)"],
                provider
            );

            const idleUsdcBalance = await usdcContract.balanceOf(VAULT_ADDRESS);

            if (idleUsdcBalance === 0n) {
                return res.status(400).json({ error: "Trade aborted: Vault has no idle USDC to deploy." });
            }

            const deployPercentage = 25n;
            const usdcAmount = (idleUsdcBalance * deployPercentage) / 100n;
            deployedUsdcFormatted = parseFloat(ethers.formatUnits(usdcAmount, 6));

            console.log(`Deploying dynamically sized trade: ${deployedUsdcFormatted} USDC`);
            tx = await vaultContract.executeBullishRebalance(indexAddress, usdcAmount);
        } else if (action === "SELL") {
            const indexContract = new ethers.Contract(
                indexAddress,
                ["function balanceOf(address) view returns(uint256)"],
                provider
            );
            const indexBalance = await indexContract.balanceOf(VAULT_ADDRESS);
            deployedUsdcFormatted = parseFloat(ethers.formatUnits(indexBalance, 18)) * 10.0;
            tx = await vaultContract.executeBearishRebalance(indexAddress, indexBalance);
        }

        const receipt = await tx.wait();
        const builderFeeUsdc = Number((deployedUsdcFormatted * (SODEX_BUILDER_FEE_BPS / 10000)).toFixed(6));
        console.log(`[Success] Vault rebalanced! Tx Hash: ${receipt.hash} | Builder Fee: $${builderFeeUsdc}`);

        return res.json({
            success: true,
            tx_hash: receipt.hash,
            builder_code: activeBuilderCode,
            deployed_usdc: deployedUsdcFormatted,
            builder_fee_usdc: builderFeeUsdc
        });

    } catch (error: any) {
        console.error(`[Execution Failed] ${error.message}`);
        return res.status(500).json({ error: error.message });
    }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Vault Execution Node running on port ${PORT} [Builder Code: ${SODEX_BUILDER_CODE}]`));