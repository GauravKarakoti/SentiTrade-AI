import { ethers, artifacts } from "hardhat";
import * as fs from "fs";
import * as path from "path";

async function main() {
  console.log("Deploying Mock SSI Ecosystem to Base Sepolia...");

  const USDC_ADDRESS = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"; // Base Sepolia USDC

  // 1. Deploy Mock Router
  const Router = await ethers.getContractFactory("MockSSIRouter");
  const router = await Router.deploy(USDC_ADDRESS);
  await router.waitForDeployment();
  const routerAddress = await router.getAddress();
  console.log(`✅ Mock SSI Router: ${routerAddress}`);

  // 2. Deploy Mock Index Tokens (FIX: Passing routerAddress)
  const Token = await ethers.getContractFactory("MockIndexToken");
  
  const mag7 = await Token.deploy("MAG7 Index", "MAG7.ssi", routerAddress);
  await mag7.waitForDeployment();
  const mag7Address = await mag7.getAddress();
  
  const defi = await Token.deploy("DeFi Index", "DEFI.ssi", routerAddress);
  await defi.waitForDeployment();
  const defiAddress = await defi.getAddress();

  const meme = await Token.deploy("Meme Index", "MEME.ssi", routerAddress);
  await meme.waitForDeployment();
  const memeAddress = await meme.getAddress();

  console.log(`✅ Mock MAG7.ssi: ${mag7Address}`);
  console.log(`✅ Mock DEFI.ssi: ${defiAddress}`);
  console.log(`✅ Mock MEME.ssi: ${memeAddress}`);

  // 3. Deploy the actual SentiTrade Vault
  console.log("\nDeploying SentiTrade AI Vault...");
  const Vault = await ethers.getContractFactory("SentiTradeVault");
  const vault = await Vault.deploy(USDC_ADDRESS, routerAddress);
  await vault.waitForDeployment();
  const vaultAddress = await vault.getAddress();
  console.log(`✅ NEW SentiTrade Vault: ${vaultAddress}`);

  // 4. Whitelist the mock tokens in the Vault
  await vault.setApprovedIndex(mag7Address, true);
  await vault.setApprovedIndex(defiAddress, true);
  await vault.setApprovedIndex(memeAddress, true);
  console.log("✅ Mock tokens whitelisted in Vault.");

  // Save the Vault ABI
  const artifact = await artifacts.readArtifact("SentiTradeVault");
  const abiDirPath = path.join(__dirname, "..", "abis");
  if (!fs.existsSync(abiDirPath)) fs.mkdirSync(abiDirPath, { recursive: true });
  fs.writeFileSync(path.join(abiDirPath, "SentiTradeVault.json"), JSON.stringify(artifact.abi, null, 2));

  console.log("\n🎉 Deployment Complete!");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});